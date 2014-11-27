#!/usr/bin/env python
# coding: utf-8
# vim: set tabstop=4 shiftwidth=4 expandtab:
"""
A few things to note as you read the documentation and source code for streamutils:
 *  the docstrings shown here are the main means of testing that the library works as promised which is why they're more
    verbose than you might otherwise expect
 *  the code is designed to run and test unmodified on python 2 & 3. That means that all prints are done via the print
    function, and strings (which are mostly unicode) can't be included in documentation output as they get 'u' prefixes
    on python 2 but not on python 3
 *  Although the examples pass in lists as the ``tokens`` argument to functions, in normal use, is unusual to use ``tokens``.
    Usually the input will come from a call to ``read`` or ``head`` or similar
 *  When a Terminator is used to pick out items (as opposed to iterating over the results of the stream) ``.close`` is called
    automatically on each of the generators in the stream. This gives each function a chance to clear up and e.g. close
    open files immediately rather than when garbage collected. If you want the same result when iterating over a stream,
    either iterate all the way to the end or call ``.close`` on the stream
 *  For now, ``#pragma: nocover`` is used to skip testing that Exceptions are thrown - these will be removed as soon as the
    normal code paths are fully tested. It is also used to skip one codepath where different code is run depending on
    which python is in use
 *  Once wrapped, ComposableFunctions return a generator that can be iterated over (or if called with ``end=True``) return
    a ``list``. Terminators return things e.g. the first item in the list (see ``first``), or a ``list`` of the items in
    the stream (see ``aslist``)

"""

from __future__ import print_function, division#, unicode_literals

from pkg_resources import parse_version 
import six
if parse_version(six.__version__) < parse_version('1.4.0'):  #pragma: nocover
    raise ImportError('six version >= 1.4.0 required')

from six import StringIO, string_types, integer_types, MAXSIZE, PY3
from six.moves import reduce, filter, filterfalse, zip   # These work - moves is a fake module
from six.moves.urllib.parse import urlparse
from six.moves.urllib.request import urlopen

import re, time, subprocess, os, glob, locale, shlex, sys, codecs, inspect

from io import open, TextIOWrapper
from contextlib import closing

from collections import Iterable, Callable, Iterator, deque, Mapping, Sequence
try:
    from collections import OrderedDict, Counter
except ImportError: # pragma: no cover
    from ordereddict import OrderedDict #To use OrderedDict backport
    from counter import Counter         #To use Counter backport
from itertools import chain, islice
from itertools import count as icount
from functools import update_wrapper

__author__= 'maxgrenderjones'
__docformat__ = 'restructuredtext'

class SHWrapper(object):
    def __getattribute__(self, name):
        if name=='__name__':
            return 'sh'
        elif name.startswith('__') and name.endwith('__'):
            #We don't want to try importing sh/pbs unless we know
            #that's what the user wants
            return super(SHWrapper, self).__getattribute__(name)
        try:
            import sh as realsh
        except ImportError:
            try:
                import pbs as realsh
            except ImportError:
                raise ImportError('Neither sh or pbs are available - sh functionality is therefore not available')
        return wrap(realsh.Command(name))

sh=SHWrapper()

class ComposableFunction(Callable):
    def __init__(self, func, tokenskw='tokens'):
        """
        Creates a composable function by wrapping func, which expects to receive tokens on its tokenskw
        :param func:
        :param tokenskw:
        """
        self.func=func
        self.tokenskw=tokenskw
        #spec = inspect.getargspec(func)
        #print('Creating Composable function for function with spec: %s' % repr(spec))

    def __call__(self, *args, **kwargs):
        #print('Calling %s via ConnectingGenerator with args %s and kwargs %s' % (self.func.__name__, args, kwargs))
        return ConnectingGenerator(self.func, self.tokenskw, list(args), kwargs)

    def __getattr__(self, name):
        f=getattr(self.func, name)
        #Kludge (ish) to allow sh's attribute access to work
        if name !='__get__' and callable(f): # Need to only follow this path if it's a sh callable.
             return wrap(f)
        else:
             return f

class ConnectingGenerator(Iterable):
    def __init__(self, func, tokenskw, args, kwargs):
        #print 'Create a ConnectingGenerator for function %s with pattern %s' % (func.__name__, args[0])
        self.func=func
        self.tokenskw=tokenskw
        self.args=args
        self.kwargs=kwargs
        #spec = inspect.getargspec(func)
        #print('Creating Connecting for function with spec: %s' % repr(spec))
        self.it=None

    def __iter__(self):
        it=self.func(*self.args, **self.kwargs)
        if isinstance(self.it, Iterator):
            pass # Function returned a genarator (or similar)
        elif isinstance(it, Iterable):
            it = it.__iter__() #Function returned a list (or similar)
        elif hasattr(it, '__iter__'): #pragma: nocover - I don't know if this is needed
            it = it.__iter__() #Function returned an iterable duck
        elif str(type(it)) in ("<class 'pbs.RunningCommand'>"): #can't compare directly in case this feature not installed
            it=iter(it.stdout.splitlines()) #stdout is a string, not an open file
        else:  #pragma: nocover
            raise TypeError('Composable Functions must return Iterators or Iterables (got %s)' % type(iter))
        self.it=it
        return self.it

    def __or__(self, other):
        if not (isinstance(other, ConnectingGenerator) or isinstance(other, Terminator)):
            raise TypeError('The ConnectingGenerator is being composed with a %s' % type(other)) #pragma: nocover

        other.kwargs[other.tokenskw]=self
        if isinstance(other, ConnectingGenerator):
            #print('Connecting output of %s to the tokens of %s' % (self.func.__name__, other.func.__name__))
            if 'end' in other.kwargs and other.kwargs['end']:
                #print('Caught end')
                other.kwargs.pop('end')
                with closing(self):
                    #print('Creating list from %s with args %s and kwargs %s' % (other.func.__name__, other.args, other.kwargs))
                    return list(other.func(*other.args, **other.kwargs))
            #print('Calling %s with args %s and kwargs %s' % (other.func.__name__, other.args, other.kwargs))
            return other
        elif isinstance(other, Terminator):
            with closing(self):
                #print('Calling %s with args %s and kwargs %s' % (other.func.__name__, other.args, other.kwargs))
                return other.func(*other.args, **other.kwargs)

    def __gt__(self, other):
        if isinstance(other, string_types) or isinstance(other, integer_types):
            with open(other, mode='w') as w:
                w.writelines((line if line.endswith('\n') else '%s%s' % (line, '\n') for line in self))
        elif hasattr(other, 'writelines'):
            other.writelines((line if line.endswith('\n') else '%s%s' % (line, '\n') for line in self))
        elif hasattr(other, 'write'):
            for line in self:
                other.write(line)
        else:  #pragma: nocover
            raise TypeError('Got %s: Can only write to filenames/file descriptors or file-like things with a write or writelines method' % other)

    def __rshift__(self, other):
        if isinstance(other, string_types) or isinstance(other, integer_types):
            with open(other, mode='a') as w:
                w.writelines((line if line.endswith('\n') else '%s%s' % (line, '\n') for line in self))
        elif hasattr(other, 'writelines'):
            other.writelines((line if line.endswith('\n') else '%s%s' % (line, '\n') for line in self))
        elif hasattr(other, 'write'):
            for line in self:
                other.write(line)
        else:  #pragma: nocover
            raise TypeError('Got %s: Can only write to filenames/file descriptors or file-like things with a write or writelines method' % other)

    def __getattr__(self, name):
        return getattr(self.func, name)

    def close(self):
        if self.it and hasattr(self.it, 'close'):
            #print('Generator for %s closing' % self.func.__name__)
            try:        # Close my generator
                self.it.close()
            finally:    #Close the previous generator if there is one
                tokens=self.kwargs.get(self.tokenskw, None)
                if tokens and hasattr(tokens, 'close'):
                    tokens.close()

class Terminator(Callable):
    def __init__(self, func, tokenskw='tokens'):
        self.func=func
        self.tokenskw=tokenskw

    def __call__(self, *args, **kwargs):
        self.args=list(args)
        self.kwargs=kwargs
        return self #We don't do anything yet, as tokens won't be set yet - func is called by the
                    #OR inside the ConnectingGenerator, after setting tokens

    def __getattr__(self, name):
        return getattr(self.func, name)

def _eopen(fname, encoding=None):
    '''
    Tries to guess what encoding to use to open a file based on first few lines. Supports xml and python
    declaration as per http://www.python.org/dev/peps/pep-0263/
    '''

    if re.search('^[a-z+]+[:][/]{2}', fname):
        return _getNewlineReadable(urlopen(fname), encoding=encoding)
    else:
        if not encoding and os.path.splitext(fname) in ['.rb', 'py']:
            encoding=head(tokens=open(fname), n=2) | search(r'coding[:=]\s*"?([-\w.]+)"?', 1) | first()
        if encoding:
            #print('Opening file %s with encoding %s' % (fname, encoding))
            return open(fname, encoding=encoding)
        else:
            #print('Opening file %s with no encoding %s' % (fname, encoding))
            return open(fname)

def _getNewlineReadable(rawstream, encoding):
    """
    TextIOWrapper before python 3.3 makes unreasonable assumptions about what attributes a readable thing has
    making it pretty much useless. The problem with ``codecs.getreader`` is that it doesn't automatically
    support universal newlines. Will close the underlying stream when finished
    :param rawstream:
    :param encoding:
    :return:
    """
    if PY3 and sys.version_info.minor>=3:  # pragma: nocover
        with closing(TextIOWrapper(rawstream, encoding=encoding)) as lines:
            for line in lines:
                yield line
    else:
        reader=codecs.getreader(encoding or locale.getpreferredencoding())
        with closing(reader(rawstream)) as lines:
            for line in lines:
                yield line


def _gettokens(fname, encoding=None, tokens=None):
    if fname:
        return _eopen(fname, encoding)
    elif tokens is not None:
        if not isinstance(tokens, Iterator):
            return iter(tokens)
        else:
            return tokens
    else: #pragma: nocover
        raise ValueError('Either fname or tokens must be set')

def _groupstodict(match, group, names, inject={}):
    """

    >>> m=re.match(r'((\w+)\s+(\w+))', 'John Smith')
    >>> d=_groupstodict(m, None, names=['Fullname', 'Firstname', 'Surname'])
    >>> for mapping in d.items():
    ...     print('%s=>%s' % mapping)
    ...
    Fullname=>John Smith
    Firstname=>John
    Surname=>Smith
    >>> d=_groupstodict(m, 0, names=['Fullname', 'Firstname', 'Surname'])
    >>> for mapping in d.items():
    ...     print('%s=>%s' % mapping)
    ...
    Fullname=>John Smith
    Firstname=>John
    Surname=>Smith

    :param match: a Match Object
    :param group: An integer group to return or a list of groups
    :param names: A dict of groups to dict keys used to form a dict to return
    :param inject: Extra key value pairs to inject into the returned dict
    :return:
    """
    #If you've specified multiple names, but haven't specified a group, then you want all groups i.e. group=None,
    #not the whole match i.e. group=0
    if names and len(names)>1 and group==0:
        group=None
    if isinstance(group, integer_types):
        if names:
            if isinstance(names, Mapping):
                d=OrderedDict((names[g], match.group(g)) for g in names)
            else:
                d=OrderedDict(zip(names, [match.group(group)]))
            if inject:
                d.update(inject)
            return d
        else:
            return match.group(group)
    else:
        if names:
            if isinstance(names, Mapping):
                d=OrderedDict((names[g], match.group(g)) for g in (group if group else names))
            else:
                d=OrderedDict(zip(names, [match.group(g) for g in group] if group else match.groups()))
            if inject:
                d.update(inject)
            return d
        else:
            if group:
                return [match.group(g) for g in group]
            else:
                return list(match.groups())

def _ntodict(results, n, names, inject={}):
    """

    :param results: an list containing the results of a e.g. ``.split`` or ``.findall`` operation
    :param group: An integer group to return or a list of groups
    :param names: A dict of groups to dict keys used to form a dict to return
    :param inject: Extra key value pairs to inject into the returned dict
    :return:
    """
    if isinstance(n, integer_types) and n>0:
        if n>0 and n>len(results):
            raise ValueError('Not enough items in list %s to pick item %d' % (results, n))
        if names:
            if isinstance(names, Mapping):
                d= OrderedDict([(names[n], results[n-1]),])
            else:
                d=OrderedDict([(names[0], results[n-1]),])
            if inject:
                d.update(inject)
            return d
        else:
            return results[n-1]
    else:
        if n and max(n)>len(results):
            raise ValueError('Not enough items in list %s to pick item %d' % (results, max(n)))
        if names:
            if isinstance(names, Mapping):
                d= OrderedDict((names[i], results[i-1]) for i in (n if n else names))
            else:
                d=OrderedDict(zip(names, [results[i-1] for i in n] if n else results))
            if inject:
                d.update(inject)
            return d
        else:
            if n:
                return [results[i-1] for i in n]
            else:
                return results

__test__ = {}
__all__ = ['sh', 'wrap', 'wrapTerminator']

def wrap(func):
    '''
    Decorator function used to create a ComposableFunction

    :param func: The function to be wrapped - should either yield items into the pipeline or return an iterable
    :param tokenskw: The keyword argument that func expects to receive tokens on
    '''
    cf=ComposableFunction(func)
    if hasattr(func, '__name__'): #sh isn't really a function
         cf = update_wrapper(cf, func)
         __test__[func.__name__]=func
         __all__.append(func.__name__)
    return cf

def wrapTerminator(func):
    """
    Used as a decorator to create a Terminator function that can end a pipeline

    :param func: The function to be wrapped - should return the desired output of the pipeline
    :param tokenskw: The keyword argument that func expects to receive tokens on
    :return: A Terminator function
    """
    t = update_wrapper(Terminator(func), func)
    __test__[func.__name__]=func
    __all__.append(func.__name__)
    return t

def _wrapInIterable(item):
    """
    Function used to ensure we have somthing we can iterate over, even if there's only one

    >>> _wrapInIterable(None)
    >>> _wrapInIterable(1)
    [1]
    >>> _wrapInIterable([1, 2])
    [1, 2]
    >>> _wrapInIterable(iter([1,2]))
    <...iterator object at ...>
    >>> _wrapInIterable(max) # Bit of a perverse example
    [<built-in function max>]

    :param item:
    :return:
    """
    if item is None:
        return None
    elif isinstance(item, integer_types) or isinstance(item, string_types):
        return [item]
    elif isinstance(item, Iterable):
        return item
    elif hasattr(item, '__iter__'): #pragma: nocover
        return item
    else:
        return [item]

@wrap
def run(command, err=False, cwd=None, env=None, encoding=None, tokens=None):
    """
    Runs a command. If command is a string then it will be split with :py:func:`shlex.split` so that it works as
    expected on windows. Runs in the same process so gathers the full output of the command as soon as it is run

    >>> from streamutils import * #Suggestions for better commands to use as examples welcome!
    >>> rev=run('git log --reverse') | search('commit (\w+)', group=1) | first()
    >>> rev == run('git log') | search('commit (\w+)', group=1) | last()
    True
    >>> #rev == sh.git.log('--reverse') | search('commit (\w+)', group=1) | first() #Alternative using sh/pbs

    :param command: Command to run
    :param err: Redirect standard error to standard out (default False)
    :param cwd: Current working directory for command
    :param env: Environment to pass into command
    :param encoding: Encoding to use to parse the output. Defaults to the default locale, or utf-8 if there isn't one
    :param tokens: Lines to pass into the command as standard in
    """
    stdin=None if tokens is None else StringIO("".join(list(tokens)))
    if isinstance(command, string_types):
        command=shlex.split(command)
    #@Todo: Change so that it uses communicate on a popen object so that the entire output doesn't need to fit in memory
    if not err:
        output=subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stdin=stdin, env=env, universal_newlines=True).stdout
    else:
        output=subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=stdin, env=env, universal_newlines=True).stdout

    if PY3:
        return output
    return _getNewlineReadable(output, encoding or locale.getdefaultlocale()[1] or 'utf-8')

@wrapTerminator
def first(default=None, tokens=None):
    """
    Returns the first item in the stream

    :param default: returned if the stream is empty
    :param tokens: a list of things
    :return: The first item in the stream
    """
    if tokens is None:
        return default
    for line in tokens:
        return line
    return default

@wrapTerminator
def last(default=None, tokens=None,):
    """
    Returns the final item in the stream

    :param default: returned if the stream is empty
    :param tokens: a list of things
    :return: The last item in the stream
    """
    out=default
    for line in tokens:
        out=line
    return out


@wrapTerminator
def aslist(tokens=None):
    """
    Returns the output of the stream as a list. Used as a a more readable alternative to calling with ``end=True``

    >>> from streamutils import *
    >>> lines=['Nimmo', 'Fish', 'Seagull', 'Nemo', 'Shark']
    >>> if matches('Nemo', tokens=['Nothing but ocean here']): #streamutils functions return generators which are always True
    ...     print('Found Nemo!')
    Found Nemo!
    >>> if matches('Nemo', tokens=lines) | aslist(): #aslist will pull out the values in the generator
    ...     print('Found Nemo!')
    Found Nemo!
    >>> if head(n=10, tokens=lines) | matches('Nemo', tokens=lines, end=True): #Note that end only works after a |
    ...     print('Found Nemo!')
    Found Nemo!

    :param tokens: Iterable object providing tokens (set by the pipeline)
    :return: a ``list`` containing all the tokens in the pipeline
    """
    return list(tokens)

@wrapTerminator
def asdict(key=None, names=None, tokens=None):
    """
    Creates a dict or dict of dicts from the result of a stream

    >>> from streamutils import *
    >>> lines=[]
    >>> lines.append('From: queen@example.com')
    >>> lines.append('To: mirror@example.com')
    >>> lines.append('Date: Once upon a time')
    >>> lines.append('Subject: The most beautiful?')
    >>> d=search('(\w+):\s*(\w.*)', tokens=lines, group=None) | asdict()
    >>> d['To']=='mirror@example.com'
    True
    >>> passwd=[] #fake output for read('/etc/passwd')
    >>> passwd.append('root:x:0:0:root:/root:/bin/bash')
    >>> passwd.append('bin:x:1:1:bin:/bin:/bin/false')
    >>> passwd.append('daemon:x:2:2:daemon:/sbin:/bin/false')
    >>> d=split(sep=':', n=1, names=['username'], tokens=passwd) | aslist()
    >>> for u in d:
    ...     print(u['username'])
    root
    bin
    daemon
    >>> d=split(sep=':', n=1, names={1: 'username'}, tokens=passwd) | aslist()  #equivalent, using a dict for names
    >>> for u in d:
    ...     print(u['username'])
    root
    bin
    daemon
    >>> d=search('^(\w+)', names=['username'], tokens=passwd) | aslist() #equivalent, using search not split
    >>> for u in d:
    ...     print(u['username'])
    root
    bin
    daemon
    >>> d=search('^(\w+)', names={1:'username'}, tokens=passwd) | aslist() #using search with a dict for names
    >>> for u in d:
    ...     print(u['username'])
    root
    bin
    daemon
    >>> d=split(sep=':', n=(1,6), names=['username', 'home'], tokens=passwd,) | asdict(key='username')
    >>> print(d['daemon']['home'])
    /sbin
    >>> d=split(sep=':', tokens=passwd) | asdict(key='username', names=['username', 'password', 'uid', 'gid', 'info', 'home', 'shell'])
    >>> print(d['root']['shell'])
    /bin/bash

    :param key: If set, key to use to construct dictionary. If ``None`` (default), input must be a list of two item tuples
    :param names: If set, list of keys that will be zipped up with the line values to create a dictionary
    :param tokens: list of key-value tuples or list of lists or dicts
    :return: :py:class:`OrderedDict`
    """
    if not key:
        return OrderedDict(tokens)
    else:
        result=OrderedDict()
        for line in tokens:
            if names:
                line=dict(zip(names,line))
            result[line[key]]=line
        return result



@wrapTerminator
def nth(n, default=None, tokens=None):
    """
    Returns the nth item in the stream, or a default if the list has less than n items

    >>> from streamutils import *
    >>> tokens = ['Flopsy', 'Mopsy', 'Cottontail', 'Peter']
    >>> rabbit = matches('.opsy', tokens=tokens) | nth(2)
    >>> print(rabbit)
    Mopsy
    >>> rabbit = matches('.opsy', tokens=tokens) | nth(3, default='No such rabbit')
    >>> print(rabbit)
    No such rabbit

    :param n: The item to return (first is 1)
    :param default: The default to use if the stream has less than n items
    :param tokens: The items in the pipeline
    :return: the nth item
    """
    cur=1
    for line in tokens:
        if cur==n:
            return line
        cur+=1
    return default

@wrapTerminator
def ssorted(cmp=None, key=None, reverse=False, tokens=None):
    """
    Sorts the output of the stream (see documentation for :py:func:`sorted`). Warning: ``cmp`` was removed from ``sorted``
    in python 3

    >>> from streamutils import *
    >>> for line in (find('*.py') | replace(os.sep, '/') | ssorted()):
    ...     print(line)
    ez_setup.py
    setup.py

    """
    if PY3: # pragma: no cover
        return sorted(tokens, key=key, reverse=reverse)
    else:
        return sorted(tokens, cmp, key, reverse)

@wrapTerminator
def smax(key=None, tokens=None):
    """
    Returns the largest item in the stream

    :param key: See documentation for :py:func:`max`
    :param tokens: a list of things
    :return: The largest item in the stream (as defined by python :py:func:`max`)
    """
    return max(tokens, key=key) if key else max(tokens)

@wrapTerminator
def smin(key=None, tokens=None):
    """
    Returns the smallest item in the stream

    :param key: See documentation for :py:func:`min`
    :param tokens: a list of things
    :return: The largest item in the stream (as defined by python :py:func:`min`)
    """
    return min(tokens, key=key) if key else min(tokens)

@wrapTerminator
def count(tokens=None):
    """
    Counts the number of items that pass through the stream (cf ``wc -l``)

    >>> from streamutils import *
    >>> lines = ['hi', 'ho', 'hi', 'ho', "it's", 'off', 'to', 'work', 'we', 'go']
    >>> matches('h.', tokens=lines) | count()
    4

    :param tokens: Things to count
    :return: number of items in the stream as an ``int``
    """
    return sum(1 for line in tokens)

@wrapTerminator
def ssum(start=0, tokens=None):
    """
    Adds the items that pass through the stream via call to :py:func:`sum`

    :param start: Initial value to start the sum, returned if the stream is empty
    :return: sum of all the values in the stream
    """
    return sum(tokens, start)

@wrapTerminator
def bag(tokens=None):
    """
    Counts the number of occurences of each of the elements of the stream

    >>> from streamutils import *
    >>> lines = ['hi', 'ho', 'hi', 'ho', "it's", 'off', 'to', 'work', 'we', 'go']
    >>> count = matches('h.', tokens=lines) | bag()
    >>> count['hi']
    2

    :param tokens: list of items to count
    :return: A :py:class:`collections.Counter`
    """
    return Counter(tokens)

@wrapTerminator
def action(func, tokens=None):
    """
    Calls a function for every element that passes through the stream

    :param func: function to call
    :param tokens: a list of things
    """
    for line in tokens:
        func(line)

@wrapTerminator
def sreduce(func, initial=None, tokens=None):
    """
    Uses a function to :py:func:`reduce` the output to a single value

    :param func: Function to use in the reduction
    :param initial: An initial value

    :return: Output of the reduction
    """
    return reduce(func, tokens, initial)

@wrapTerminator
def write(fname=None, encoding=None, tokens=None):
    r"""
    Writes the output of the stream to a file, or via ``print`` if no file is supplied. Calls to ``print`` include
    a call to :py:func:`str.rstrip` to remove trailing newlines

    >>> from streamutils import *
    >>> from six import StringIO
    >>> lines=['%s\n' % line for line in ['Three', 'Blind', 'Mice']]
    >>> head(tokens=lines) | write() # By default prints to the console
    Three
    Blind
    Mice
    >>> buffer = StringIO() # Alternatively write to an open filelike object
    >>> head(tokens=lines) | write(fname=buffer)
    >>> writtenlines=buffer.getvalue().splitlines()
    >>> writtenlines[0]=='Three'
    True

    :param fname: If `str`, filename to write to, otherwise open file-like object to write to. Default of `None` implies
                    write to standard output
    :param encoding: Encoding to use to write to the file
    :param tokens: Lines to write to the file
    """
    if tokens:
        if not fname:
            for line in tokens:
                print(line.rstrip() if isinstance(line, string_types) else line)
        elif isinstance(fname, string_types):
            with open(fname, encoding=encoding, mode='wt') as f:
                f.writelines(tokens)
        else:
            for line in tokens:
                fname.write(line)

@wrap
def unique(tokens=None):
    """
    Passes through values the first time they are seen

    >>> from streamutils import *
    >>> lines=['one', 'two', 'two', 'three', 'three', 'three', 'one']
    >>> unique(lines) | write()
    one
    two
    three

    :param tokens: Either set by the pipeline or provided as an initial list of items to pass through the pipeline
    """
    s=set()
    for line in tokens:
        if line not in s:
            s.add(line)
            yield line

@wrap
def head(n=10, fname=None, skip=0, encoding=None, tokens=None):
    """
    (Optionally) opens a file and passes through the first ``n`` items

    >>> from streamutils import *
    >>> lines=['Film,Character,Animal', 'Finding Nemo,Nemo,Fish', 'Shrek,Shrek,Ogre', 'The Jungle Book,Baloo,Bear']
    >>> head(3, tokens=lines) | write()
    Film,Character,Animal
    Finding Nemo,Nemo,Fish
    Shrek,Shrek,Ogre
    >>> head(2, skip=1, tokens=lines) | write()
    Finding Nemo,Nemo,Fish
    Shrek,Shrek,Ogre
    >>> head(n=0, skip=1, tokens=lines) | split(sep=',', names=['film', 'name', 'animal']) | sformat('The film {film} stars a {animal} called {name}') | write()
    The film Finding Nemo stars a Fish called Nemo
    The film Shrek stars a Ogre called Shrek
    The film The Jungle Book stars a Bear called Baloo
    >>> head(n=[1,3], skip=1, tokens=lines) | split(sep=',', names=['film', 'name', 'animal']) | sformat('The film {film} stars a {animal} called {name}') | write()
    The film Finding Nemo stars a Fish called Nemo
    The film The Jungle Book stars a Bear called Baloo

    :param n: Number of lines to return (0=all lines) or a list of lines to return
    :param fname: Filename (or filenames) to open
    :param skip: Number of lines to skip before returning lines
    :param encoding: Encoding of file to open. If None, will try to guess the encoding based on coding= strings
    :param tokens: Stream of tokens to take the first few members of (i.e. not a list of filenames to take the first few lines of)
    """
    fnames=_wrapInIterable(fname) or [iter(tokens)] #Bit ugly, but we want to make sure iterating through tokens skips them, even if tokens is a list
    for name in fnames:
        tokens=_eopen(name, encoding) if fname else name
        try:
            if isinstance(n, integer_types):
                for line in islice(tokens, skip, skip+n if n else MAXSIZE):
                    yield line
            else:
                if skip:
                    for i, line in zip(range(0,skip), tokens):
                        pass
                start=1
                for num in n:
                    for i, line in zip(icount(start), tokens):
                        if i==num:
                            yield line
                            break
                    start=i+1
        finally:
            if fname and tokens:
                tokens.close()

@wrap
def tail(n=10, fname=None, encoding=None, tokens=None):
    """
    Returns a list of the last ``n`` items in the stream

    >>> tokens="hi ho hi ho it's off to work we go".split()
    >>> tail(5, tokens=tokens) | write()    #Note tail() returns a deque not a generator, but it still works as part of a stream
    off
    to
    work
    we
    go
    >>> tail(2, fname='ez_setup.py') | write()
    if __name__ == '__main__':
        sys.exit(main())

    :param n: How many items to return e.g. ``n=5`` will return 5 items
    :param fname: A filename from which to read the last ``n`` items (10 by default)
    :param encoding: The enocding of the file
    :param tokens: Will be set by the chain
    :return: A list of the last ``n`` items
    """
    try:
        tokens=_gettokens(fname, encoding, tokens) #@todo: change to match head
        if tokens is not None:
            return deque(tokens, n)
        else: #pragma: nocover
            ValueError('Either fname or tokens must be set')
    finally:
        if fname and tokens:
            tokens.close()

@wrap
def sslice(start=1, stop=MAXSIZE, step=1, fname=None, encoding=None, tokens=None):
    """
    Provides access to a slice of the stream between ``start`` and ``stop`` at intervals of ``step``

    >>> lines="hi ho hi ho it's off to work we go".split()
    >>> sslice(start=2, stop=10, step=2, tokens=lines) | write() #start and stop are both relative to the first item
    ho
    ho
    off
    work
    >>> sslice(start=1, stop=7, step=3, fname='ez_setup.py') | write()
    #!/usr/bin/env python
    To use setuptools in your package's setup.py, include this

    :param start: First token to return (first is 1)
    :param stop: Maximum token to return (default some very large number - effectively read to the end)
    :param step: Interval between tokens
    :param fname: Filename to use as input
    :param encoding: Unicode encoding to use to open files
    :param tokens: list of filenames to open
    """
    try:
        tokens=_gettokens(fname, encoding, tokens) #@todo: change to match head
        for line in islice(tokens, start-1, stop-1, step):
            yield line
    finally:
        if fname and tokens:
            tokens.close()

@wrap
def follow(fname, encoding=None): #pragma: nocover - runs forever!
    """
    Monitor a file, reading new lines as they are added (equivalent of `tail -f` on UNIX). (Note: Never returns)

    :param fname: File to read
    :param encoding: encoding to use to read the file
    """
    f = _eopen(fname, encoding)
    f.seek(0, os.SEEK_END)
    while True:
        line = f.readline()
        if not line:
            time.sleep(1)
            continue
        yield line

@wrap
def bzread(fname=None, encoding=None, tokens=None):
    """
    Read a file or files from bzip2-ed archives and output the lines within the files.

    >>> find('examples/*.bz2') | bzread() | head(1) | write()
    199.72.81.55 - - [01/Jul/1995:00:00:01 -0400] "GET /history/apollo/ HTTP/1.0" 200 6245

    :param fname:  filename or `list` of filenames
    :param encoding: unicode encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames
    """
    from bz2 import BZ2File
    files=_wrapInIterable(fname) if fname else tokens
    for name in files:
        if PY3 and sys.version_info.minor>=3:  #pragma: nocover
                from bz2 import open as bzopen
                with bzopen(name, 'rt', encoding=encoding) as lines:
                    for line in lines:
                        yield line
        else:
            for line in _getNewlineReadable(BZ2File(name, 'rb'), encoding):
                yield line

@wrap
def gzread(fname=None, encoding=None, tokens=None):
    """
    Read a file or files from gzip-ed archives and output the lines within the files.

    :param fname:  filename or `list` of filenames
    :param encoding: unicode encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames
    """
    from gzip import open as gzopen
    files=_wrapInIterable(fname) if fname else tokens
    if files is None:  #pragma: nocover
        raise ValueError('No filename or stream supplied')
    for name in files:
        if PY3 and sys.version_info.minor>=3: #pragma: nocover
            with gzopen(name, 'rt', encoding=encoding) as lines:
                for line in lines:
                    yield line
        else:
            for line in _getNewlineReadable(gzopen(name, 'rb'), encoding=encoding):
                yield line

@wrap
def read(fname=None, encoding=None, tokens=None):
    """
    Read a file or files and output the lines it contains. Files are opened with :py:func:`io.read`

    >>> from streamutils import *
    >>> read('https://raw.github.com/maxgrenderjones/streamutils/master/README.md') | search('^[-] Source Code: (.*)', 1) | write()
    http://github.com/maxgrenderjones/streamutils

    :param fname: filename or `list` of filenames. Can either be paths to local files or URLs (e.g. http:// or ftp:// - supports the same protocols as :py:func:`urllib2.urlopen`)
    :param encoding: encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames
    """
    if fname or tokens:
        files=_wrapInIterable(fname) if fname else tokens
        for name in files:
            with closing(_eopen(name, encoding)) as f:
                for line in f:
                    yield line
    else:  #pragma: nocover
        import fileinput
        for line in fileinput.input('-'):
            yield line

@wrap
def search(pattern, group=0, to=None, match=False, fname=None, encoding=None, names=None, inject={}, flags=0,
           strict=False, tokens=None):
    """
    Looks for a regexp pattern within each token (by default by search, but alternatively by match)
    and pass through matches, a group or a regexp substitution

    >>> from streamutils import *
    >>> lines = ['Jiminy Cricket Pinocchio Geppetto']
    >>> search(r'P(\w)+o', tokens=lines) | write()
    Pinocchio
    >>> search(r'(P(\w)+o)', to='Real Boy', tokens=lines) | write()
    Jiminy Cricket Real Boy Geppetto
    >>> sw ='Snow White'
    >>> dwarves = 'Dwarf One Dwarf Two Dwarf Three Dwarf Four Dwarf Five Dwarf Six Dwarf Seven'
    >>> search(r'(Dwarf \w+\s*){7}', to='The Seven Dwarves', tokens=[dwarves]) | write()
    The Seven Dwarves
    >>> search(r'(Dwarf \w+\s*){7}', to='The Seven Dwarves', match=True, tokens=[dwarves]) | write()
    The Seven Dwarves
    >>> search(r'(Dwarf \w+\s*){7}', to='The Seven Dwarves', match=True, tokens=['%s and %s' % (sw, dwarves)]) | write()
    >>> search(r'(Dwarf \w+\s*){7}', to='The Seven Dwarves', tokens=['%s and %s' % (sw, dwarves)]) | write()
    Snow White and The Seven Dwarves

    :param pattern: Pattern to look for
    :param group: Group (``int``) or groups (``list`` of `int`s or match names) to return. (Note: 0 returns the whole match,
            None returns the matches in a group as a list)
    :param to: Regexp substition pattern to return - uses :py:func:`re.sub`
    :param match: ``True`` - use :py:func:`re.search`, ``False`` (default) use :py:func:`re.match`
    :param fname: Filename (or list of flienames) to search through
    :param encoding: Encoding to use to open the files
    :param names: dict of groups to names - if included, result will be a dict
    :param inject: Used in conjunction with names, a `dict` of key: values to inject into the results dictionary
    :param strict: If True, raise a ValueError if every line doesn't match the pattern (default False)
    :param flags: Regexp flags to use
    :param tokens: strings to search through
    """
    matcher = re.compile(pattern) if not flags else re.compile(pattern, flags=flags)
    if fname is not None:
        tokens=read(fname, encoding)
    for line in tokens:
        result = matcher.match(line) if match else matcher.search(line)
        if not result and strict:
            raise ValueError('%s does not match pattern %s' % (line, pattern))
        if to:
            if match:
                if result:
                    yield matcher.sub(to, line)
            else:
                yield matcher.sub(to, line)
        else:
            if result:
                yield _groupstodict(result, group, names, inject)

@wrap
def replace(old, new, tokens=None):
    """
    Replace ``old`` in each tokens with ``new`` via call to ``.replace`` on each token (e.g. :py:func:`str.replace`)

    :param old: text to replace
    :param new: what to replace it with
    :param tokens: typically a series of strings
    """
    for line in tokens:
        yield line.replace(old, new)

@wrap
def matches(pattern, match=False, flags=0, v=False, tokens=None):
    """
    Filters the input for strings that match the pattern (think UNIX ``grep``)

    >>> months=['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    >>> matches('A', tokens=months) | write()
    April
    August

    :param pattern: regexp pattern to test against
    :param match: if ``True``, use :py:func:`re.match` else use :py:func:`re.search` (default ``False``)
    :param flags: regexp flags
    :param v: if ``True``, return strings that don't match (think UNIX ``grep -v``) (default ``False``)
    :param tokens: strings to match
    """
    matcher=re.compile(pattern) if not flags else re.compile(pattern, flags=flags)
    #print 'tokens type %s' %  type(tokens)
    for line in tokens:
        #print 'Running line %s (type: %s) against %s' % (line, type(line), pattern)
        assert isinstance(line, string_types)
        result = matcher.match(line) if match else matcher.search(line)
        if result and not v:
            yield line
        elif v and not result:
            yield line
@wrap
def nomatch(pattern, match=False, flags=0, tokens=None):
    """
    Filters the input for strings that don't match the pattern (think UNIX ``grep -v``)

    >>> months=['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    >>> nomatch('r|a', flags=re.IGNORECASE, tokens=months) | write()
    June
    July


    :param pattern: regexp pattern to test against
    :param match: if ``True``, use :py:func:`re.match` else use :py:func:`re.search` (default ``False``)
    :param flags: regexp flags
    :param tokens: strings to match
    """
    for token in matches(pattern=pattern, flags=flags, match=match, v=True, tokens=tokens):
        yield token

@wrap
def fnmatches(pathpattern, matchcase=False, tokens=None):
    """
    Filter tokens for strings that match the pathpattern using :py:func:`fnmatch.fnmatch` or :py:func:`fnmatch.fnmatchcase`.
    Note that ``os.sep`` (i.e. ``\\`` on windows) will be replaced with ``/`` to allow ``/`` to be used in the pattern

    >>> from streamutils import *
    >>> lines = ['setup.py', 'README.md', 'streamutils/__init__.py']
    >>> fnmatches('*.py', False, lines) | write()
    setup.py
    streamutils/__init__.py
    >>> fnmatches('*/*.py', False, lines) | write()
    streamutils/__init__.py
    >>> fnmatches('readme.*', True, lines) | write()
    >>> fnmatches('README.*', True, lines) | write()
    README.md


    :param pathpattern: Pattern to match (caution - ``/`` or ``os.sep`` is not special)
    :param matchcase: Whether to match case-senitive on case-insensitive file systems
    :param tokens: list of filename strings to match
    """
    import fnmatch
    for line in tokens:
        line.replace(os.sep, '/')
        if matchcase and fnmatch.fnmatchcase(line, pathpattern):
            yield line
        elif not matchcase and fnmatch.fnmatch(line, pathpattern):
            yield line
@wrap
def find(pathpattern=None, tokens=None):
    """
    Searches for files the match a given pattern. For example

    >>> from streamutils import *
    >>> find('src/*.py') | replace(os.sep, '/') | write()    #Only searches src directory
    >>> find('src/*/*.py') | replace(os.sep, '/') | write() #Searches full directory tree
    src/streamutils/__init__.py

    :param pathpattern: :py:func:`glob.glob`-style pattern
    :param tokens: A list of ``glob``-style patterns to search for
    :return: An iterator across the filenames found by the function
    """
    paths=_wrapInIterable(pathpattern) if pathpattern else tokens
    if paths:
        return chain.from_iterable(glob.iglob(path) for path in paths)
    else:
        return glob.iglob('**/*')

@wrap
def words(n=0, word=r'\S+', outsep=None, names=None, inject=None, flags=0, tokens=None):
    r"""
    Words looks for non-overlapping strings that match the word pattern. It passes on the words it finds down
    the stream. If outsep is None, it will pass on a list, otherwise it will join together the selected words with
    outsep

    >>> from streamutils import *
    >>> tokens=[str('first second third'), str(' fourth fifth sixth ')]
    >>> words(1, tokens=tokens) | write()
    first
    fourth
    >>> words([1], tokens=tokens) | write()
    ['first']
    ['fourth']
    >>> words((1,3), tokens=tokens) | write()
    ['first', 'third']
    ['fourth', 'sixth']
    >>> words((1,3), outsep=' ', tokens=tokens) | write()
    first third
    fourth sixth
    >>> words((1,), names=(1,), tokens=tokens) | write()
    OrderedDict([(1, 'first')])
    OrderedDict([(1, 'fourth')])
    >>> words(word="[\w']+", tokens=[str("What's up?")]) | write() #Note how the output is different from split()
    ["What's", 'up']

    :param n: an integer indicating which word to return (first word is 1), a list of integers to select multiple words, or 0 to return all words. If
        n is an integer, the result is a string, if n is a list, the result is a list of strings
    :param word: a pattern that will be used to select words using :py:func:`re.findall` - (default \S+)
    :param outsep: a string separator to join together the words that are found into a new string (or None to output a list of words)
    :param names: (Optional) a name or list of names of the n extracted words, used to construct a dict to be passed down the pipeline
    :param inject: For use with ``names`` - extra key/value pairs to include in the output dict
    :param flags: flags to pass to the re engine to compile the pattern
    :param tokens: list of tokens to iterate through in the function (usually supplied by the previous function in the pipeline)
    :raise: ``ValueError`` if there are less than n (or max(n)) words in the string
    """
    matcher=re.compile(word) if not flags else re.compile(word, flags=flags)
    for line in tokens:
        result=matcher.findall(line)
        yield _ntodict(result, n, names, inject) if not outsep else outsep.join(_ntodict(result, n, names, inject))

@wrap
def split(n=0, sep=None, outsep=None, names=None, inject={}, tokens=None):
    """
    split separates the input using `.split(sep)`, by default splitting on whitespace (think :py:func:`str.split`)

    >>> split(tokens=[str("What's up?")]) | write() #Note how the output is different from words
    ["What's", 'up?']
    >>> split(1, tokens=[str("What's up?")]) | write() #if n is an int, then a string is returned
    What's

    :param n: int or list of ints determining which word to pick (first word is 1), 0 returns the whole list
    :param sep: string separator to split on - by default ``sep=None`` which splits on whitespace
    :param outsep: if not None, output will be joined using this separator
    :param names: (Optional) a name or list of names of the n extracted words, used to construct a dict to be passed down the pipeline
    :param inject: For use with ``names`` - extra key/value pairs to include in the output dict
    :param tokens: strings to split
    """
    if tokens is None:
        raise ValueError('No stream supplied')
    for line in tokens:
        result=line.split(sep)
        yield _ntodict(result, n, names, inject) if not outsep else outsep.join(_ntodict(result, n, names, inject))
@wrap
def join(sep=None, tokens=None):
    """
    Joins a list-like thing together using the supplied `sep` (think :py:func:`str.split`)
    """
    if tokens is None:
        raise ValueError('No stream supplied')
    for line in tokens:
        yield sep.join(line)

@wrap
def convert(converters, defaults={}, tokens=None):
    """
    Takes a ``dict`` or ``list`` of tokens and calls the supplied converter functions.

    >>> from streamutils import *
    >>> lines=['Alice in Wonderland 1951', 'Dumbo 1941']
    >>> search('(.*) (\d+)',group=None, tokens=lines) | sformat('{0} was filmed in {1}') | write()
    Alice in Wonderland was filmed in 1951
    Dumbo was filmed in 1941
    >>> search('(.*) (\d+)', group=None, tokens=lines) | convert({2: int}) | sformat('{0} was filmed in {1:d}') | write() #Note it's the second field
    Alice in Wonderland was filmed in 1951
    Dumbo was filmed in 1941
    >>> search('(.*) (\d+)', group=None, names=['Title', 'Year'], tokens=lines) | convert({'Year': int}) | sformat('{0} was filmed in {1:d}') | write()
    Alice in Wonderland was filmed in 1951
    Dumbo was filmed in 1941
    >>> convert({'Number': int}, defaults={'Number': 42}, tokens=[{'Number': '0'}, {'Number': 'x'}]) | sformat('{Number:d}') | write()
    0
    42
    >>> convert(int, defaults=42, tokens=['0', 'x']) | write()
    0
    42

    :param converters: ``dict`` of functions or ``list`` of functions or function that converts a field from one form to another
    :param defaults: defaults to use if the converter function raises a ``ValueError`` (should be the same type as converters)
    :param tokens: a series of ``dict`` or ``list`` of things to be converted or a series of things
    :raise: ``ValueError`` if the conversion fails and no default is supplied
    """
    for line in tokens:
        if isinstance(converters, Sequence) or isinstance(converters, Mapping):
            for field in converters:
                try:
                    if isinstance(line, Sequence):
                        line[field-1]=converters[field](line[field-1])
                    elif isinstance(line, Mapping):
                        line[field]=converters[field](line[field])
                except ValueError:
                    if field in defaults:
                        line[field]=defaults[field]
                    else:
                        raise
        else:
            try:
                line=converters(line)
            except ValueError:
                if defaults is not None:
                    line=defaults
                else:
                    raise
        yield line

@wrap
def transform(transformation, tokens=None):
    """
    Applies a transformation function to each element of the stream

    >>> from streamutils import *
    >>> transform(lambda x: x.upper(), ['aeiou']) | write()
    AEIOU

    :param transformation: function to apply
    :param tokens: list/iterable of objects
    """
    for line in tokens:
        yield transformation(line)

@wrap
def strip(tokens=None):
    r"""
    Runs ``.strip`` against each line of the stream

    >>> from streamutils import *
    >>> line=strip(tokens=['  line\n']) | first()
    >>> line=='line'
    True

    :param tokens: A series of lines to remove whitespace from
    """
    return transform(lambda x: x.strip(), tokens)

@wrap
def sfilter(filterfunction=None, tokens=None):
    """

    Take a user-defined function and passes through the tokens for which the function returns something that is True
    in a conditional context. If no function is supplied, passes through the True items. (Equivalent of :py:func:`filter`)
    function

    >>> sfilter(lambda x: x%3==0, tokens=[1,3,4,5,6,9]) | write()
    3
    6
    9
    >>> sfilter(lambda x: x.endswith('ball'), tokens=['football', 'rugby', 'tennis', 'volleyball']) | write()
    football
    volleyball

    :param filterfunction: function to use in the filter
    :param tokens: list of tokens to iterate through in the function (usually supplied by the previous function in the pipeline)
    """
    for line in filter(filterfunction, tokens):
        yield line

@wrap
def sfilterfalse(filterfunction=None, tokens=None):
    """
    Passes through items for which the output of the filter function is False in a boolean context

    >>> sfilterfalse(lambda x: x.endswith('ball'), tokens=['football', 'rugby', 'tennis', 'volleyball']) | write()
    rugby
    tennis

    :param filterfunction: Function to use for filtering
    :param tokens: List of things to filter
    """
    for line in filterfalse(filterfunction, tokens):
        yield line

@wrap
def sformat(pattern, tokens=None):
    """
    Takes in a list or dict of strings and formats them with the supplied pattern

    >>> from streamutils import *
    >>> lines = [['Rapunzel', 'tower'], ['Shrek', 'swamp']]
    >>> sformat('{0} lives in a {1}', lines) | write()
    Rapunzel lives in a tower
    Shrek lives in a swamp
    >>> lines = [{'name': 'Rapunzel', 'home': 'tower'}, {'name': 'Shrek', 'home': 'swamp'}]
    >>> sformat('{name} lives in a {home}', lines) | write()
    Rapunzel lives in a tower
    Shrek lives in a swamp

    :param pattern: New-style python formatting pattern (see :py:func:`str.format`)
    :param tokens: list of lists of fomatting arguments or list of mappings
    """
    for token in tokens:
        if isinstance(token, Sequence):
            yield pattern.format(*token)
        elif isinstance(token, Mapping):
            yield pattern.format(*token.values(), **token)
        else:  # pragma: nocover
            raise TypeError('Format expects a sequence or a mapping - got a %s' % type(token))
