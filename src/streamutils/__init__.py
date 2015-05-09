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
 *  Although the examples pass in lists as the ``tokens`` argument to functions, in normal use it is unusual to use ``tokens``.
    Usually the input will come from a call to ``read`` or ``head`` or similar
 *  When a Terminator is used to pick out items (as opposed to iterating over the results of the stream) ``.close`` is called
    automatically on each of the generators in the stream. This gives each function a chance to clear up and e.g. close
    open files immediately rather than when garbage collected. If you want the same result when iterating over a stream,
    either iterate all the way to the end or call ``.close`` on the stream
 *  For now, ``#pragma: no cover`` is used to skip testing that Exceptions are thrown - these will be removed as soon as the
    normal code paths are fully tested. It is also used to skip one codepath where different code is run depending on
    which python is in use to give a correct overall coverage report
 *  Once wrapped, ConnectedFunctions return a generator that can be iterated over (or if called with ``end=True``) return
    a ``list``. Terminators return things e.g. the first item in the list (see ``first``), or a ``list`` of the items in
    the stream (see ``aslist``)

"""

from __future__ import print_function, division#, unicode_literals

from pkg_resources import parse_version 
import six
if parse_version(six.__version__) < parse_version('1.4.0'):  #pragma: no cover
    raise ImportError('six version >= 1.4.0 required')

from six import StringIO, string_types, integer_types, MAXSIZE, PY2, PY3
from six.moves import reduce, map, filter, filterfalse, zip   # These work - moves is a fake module
from six.moves.urllib.parse import urlparse
from six.moves.urllib.request import urlopen

import re, time, subprocess, os, glob, locale, shlex, sys, codecs, inspect, heapq, bz2, gzip

from io import open, TextIOWrapper
from contextlib import closing, contextmanager

from collections import Iterable, Callable, Iterator, deque, Mapping, Sequence
try:
    from collections import OrderedDict, Counter
except ImportError: # pragma: no cover
    from ordereddict import OrderedDict #To use OrderedDict backport
    from counter import Counter         #To use Counter backport
from itertools import chain as ichain, islice, count as icount, takewhile as itakewhile, dropwhile as idropwhile, groupby as igroupby
from functools import update_wrapper, partial

from .version import __version__

__author__= 'maxgrenderjones'
__docformat__ = 'restructuredtext'


class Connector(Iterable):

    def __init__(self, func, tokenskw='tokens'):
        #print 'Create a Connector for function %s with pattern %s' % (func.__name__, args[0])
        self.func=func
        self.tokenskw=tokenskw
        self.it=None # Required to be able to implement close

    def __call__(self, *args, **kwargs):
        """
        When our Connector is called we want to return a new Connector, but this time with a wrapped function.
        Otherwise using the same function twice in a pipeline can lead to a loop

        >>> head(n=10, fname='setup.py') | head(n=1) | first() | write() 
        #!/usr/bin/env python

        Even if the function is never called, it is wrapped in a partial func when __or__ is called
        >>> head(n=10, fname='setup.py') | head | first() | write()
        #!/usr/bin/env python

        """
        return Connector(update_wrapper(partial(self.func, *args, **kwargs), self.func), self.tokenskw)

    def __iter__(self):
        it=self.func()
        if isinstance(it, Iterator):
            pass # Function returned a generator (or similar)
        elif isinstance(it, Iterable):
            it=it.__iter__() #Function returned a list (or similar)
        elif hasattr(it, '__iter__'): #pragma: no cover - I don't know if this is needed
            it=it.__iter__() #Function returned an iterable duck
        else:  #pragma: no cover
            raise TypeError('functions wrapped in Connectors must be either generators or return Iterators or Iterables (got %s)' % type(iter))
        self.it=it
        return self.it

    def __or__(self, other):
        if isinstance(other, Connector) or isinstance(other, Terminator):
            return other.__ror__(self)
        else:
            raise NotImplementedError('Cannot compose a Connector with a %s' % type(other))

    def __ror__(self, other):
        """ 
        Note that if the self is not the first element in the pipeline its __ror__ method will be called *before* __call__
        """
        other = other if isinstance(other, Iterable) else _wrapInIterable(other)
        if not hasattr(self.func, 'keywords'): # We've never been called, so func isn't a partial
            self.func=update_wrapper(partial(self.func, **{self.tokenskw: other}), self.func)
        self.func.keywords[self.tokenskw]=other
        if self.func.keywords.pop('end', False):
            with closing(self):
                return list(self.func())
        else:
            return self

    def __gt__(self, other):
        return self | smap(lambda x: x if x.endswith('\n') else x+'\n') | write(other, mode='wt') # without \n, no newline is added to the end of each token
        
    def __rshift__(self, other):
        return self | smap(lambda x: x if x.endswith('\n') else x+'\n') | write(other, mode='at') # without \n, no newline is added to the end of each token

    def __getattr__(self, name):
        """Ensures that docstrings from wrapped function are returned, not Terminator"""
        return getattr(self.func, name)

    def close(self):
        if self.it and hasattr(self.it, 'close'):
            #print('Generator for %s closing' % self.func.__name__)
            try:        # Close my generator
                self.it.close()
            finally:    #Close the previous generator if there is one
                if hasattr(self.func, 'keywords'): 
                    tokens=self.func.keywords.get(self.tokenskw, None)
                    if tokens and hasattr(tokens, 'close'):
                        tokens.close()

class Terminator(Callable):
    def __init__(self, func, tokenskw='tokens'):
        self.func=func
        self.tokenskw=tokenskw

    def __ror__(self, other):
        if not (isinstance(other, Iterable)):
            raise NotImplementedError('Cannot compose a Connector with a %s' % type(other)) #pragma: no cover
        try:
            return self.func(**{self.tokenskw: _wrapInIterable(other)})
        finally:
            if other and hasattr(other, 'close'):
                other.close()

    def __call__(self, *args, **kwargs):
        #We don't do anything yet, as tokens won't be set yet - func is called by the OR inside the Connector, after setting tokens
        return Terminator(update_wrapper(partial(self.func, *args, **kwargs), self.func), tokenskw=self.tokenskw)

    def __getattr__(self, name):
        """Ensures that docstrings from wrapped function are returned, not Terminator"""
        return getattr(self.func, name)

@contextmanager
def _noopcontext(arg):
    '''Dummy context manager that can be used in a with block without actually doing anything'''
    yield arg

@contextmanager
def _wrappedopen(openfunc, fname, encoding, mode=True):
    #Horrible special-cased hacks
    if PY3 and openfunc==urlopen: # pragma: no cover
        with urlopen(fname) as f:
            with TextIOWrapper(f, encoding=encoding) as t:
                yield t
    elif PY3 and sys.version_info.minor>=3: # pragma: no cover
        with openfunc(fname, mode='rt', encoding=encoding) as f:
            yield f
    elif openfunc==urlopen or PY2 and sys.version_info[1]==6 and openfunc==gzip.open:
        with closing(openfunc(fname)) as f:
            yield codecs.getreader(encoding or locale.getpreferredencoding())(f)
    else:
        # Abominable hacks, as you can't assign attributes to a C-drived thing like BZ2File
        # and under python2.6 gzip doesn't have a seekable attribute
        from collections import namedtuple
        from types import MethodType
        fileapi=namedtuple('fileapi', ['read', 'read1', 'close', 'closed'])
        fileapi.readable = lambda self: True
        fileapi.writable = lambda self: False
        fileapi.seekable = lambda self: False
        fileapi.flush = lambda self: 0 # Flush shouldn't be called for reads
        with openfunc(fname, mode='rb') if sys.version_info[1]==7 and mode \
                else closing(openfunc(fname, mode='rb')) if mode           \
                else closing(openfunc(fname)) as f:
            fa=fileapi(f.read, f.read, f.close, f.closed)
            with TextIOWrapper(fa, encoding=encoding) as t:
                yield t

@contextmanager            
def _eopen(fname, encoding=None):
    '''
    Tries to guess what encoding to use to open a file based on first few lines. Supports xml and python
    declaration as per http://www.python.org/dev/peps/pep-0263/

    Can transparently read from gzip, bzip or xz files (with backports.lzma if necessary), but then encoding support is dependent on 
    underlying python support (2.x does not support encoding)
    TODO: use _getNewlineReadable to support encoding
    '''

    encoding=encoding or sys.getdefaultencoding()
    encoding='utf-8' if encoding=='ascii' else encoding

    if re.search('^[a-z+]+[:][/]{2}', fname):
        with _wrappedopen(urlopen, fname, encoding, mode=False) as f:
            yield f
    else:
        ext=os.path.splitext(fname)[1]
        if ext in ['.gz', '.gzip']:
            openfunc=gzip.open
        elif ext in ['.bz2', ]:
            openfunc=bz2.BZ2File if not PY3 or sys.version_info.minor<3 else bz2.open
        elif ext in ['.xz', ]:
            try:
                import lzma
            except:
                try:
                    from backports import lzma
                except: # pragma: no cover
                    print('lzma module required to open .xz files - try installing backports.lzma')
                    raise
            openfunc=lzma.open
        else:
            openfunc=open
        if not encoding and os.path.splitext(fname) in ['.rb', 'py']:
            with _wrappedopen(openfunc, fname, encoding) as f:
                encoding=head(tokens=f, n=2) | search(r'coding[:=]\s*"?([-\w.]+)"?', 1) | first()
        #print('Opening file %s with encoding %s' % (fname, encoding))
        with _wrappedopen(openfunc, fname, encoding) as f:
            yield f

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

    :param results: a list containing e.g. the results of a ``.split`` or ``.findall`` operation
    :param group: An integer group to return or a list of groups
    :param names: A dict of group number to dict keys used to form a dict to return
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
__all__ = ['connector', 'terminator']

def connector(func):
    '''
    Decorator used to wrap a function in a Connector 

    :param func: The function to be wrapped - should either yield items into the pipeline or return an iterable
    :param tokenskw: The keyword argument that func expects to receive tokens on
    '''
    cf = update_wrapper(Connector(func), func)
    __test__[func.__name__]=func
    __all__.append(func.__name__)
    return cf

def terminator(func):
    """
    Decorator used to wrap a function in a Terminator that ends a pipeline

    :param func: The function to be wrapped - should return the desired output of the pipeline
    :param tokenskw: The keyword argument that func expects to receive tokens on
    :return: A Terminator function
    """
    t=update_wrapper(Terminator(func), func)
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
    elif hasattr(item, '__iter__'): #pragma: no cover
        return item
    else:
        return [item]

@connector
def run(command, err=False, cwd=None, env=None, tokens=None):
    """
    Runs a command. If command is a string then it will be split with :py:func:`shlex.split` so that it works as
    expected on windows. Current implementation runs in the same process so gathers the full output of the command 
    before passing output to subsequent functions.

    >>> from streamutils import * #Suggestions for better commands to use as examples welcome!
    >>> rev=run('git log --reverse') | search('commit (\w+)', group=1) | first()
    >>> rev == run('git log') | search('commit (\w+)', group=1) | last()
    True

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
    return output

@terminator
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

@terminator
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


@terminator
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

@terminator
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



@terminator
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
    return next(islice(tokens, n-1, None), default) # See nth recipe in https://docs.python.org/2/library/itertools.html#itertools.islice

@terminator
def ssorted(cmp=None, key=None, reverse=False, tokens=None):
    """
    Sorts the output of the stream (see documentation for :py:func:`sorted`). Warning: ``cmp`` was removed from ``sorted``
    in python 3

    >>> from streamutils import *
    >>> for line in (find('*.py') | replace(os.sep, '/') | ssorted()):
    ...     print(line)
    ez_setup.py
    setup.py

    :return: a sorted list
    """
    if PY3: # pragma: no cover
        return sorted(tokens, key=key, reverse=reverse)
    else:
        return sorted(tokens, cmp=cmp, key=key, reverse=reverse)

@terminator
def nsmallest(n, key=None, tokens=None):
    """
    Returns the n smallest elements of the stream (see documentation for :py:func:`heapq.nsmallest`)

    >>> from streamutils import *
    >>> head(10, tokens=range(1,10)) | nsmallest(4)
    [1, 2, 3, 4]
    """
    return heapq.nsmallest(n, tokens, key) if key else heapq.nsmallest(n, tokens)


@terminator
def nlargest(n, key=None, tokens=None):
    """
    Returns the n largest elements of the stream (see documentation for :py:func:`heapq.nlargest`)

    >>> from streamutils import *
    >>> head(10, tokens=range(1,10)) | nlargest(4)
    [9, 8, 7, 6]
    """
    return heapq.nlargest(n, tokens, key) if key else heapq.nlargest(n, tokens)

@terminator
def smax(key=None, tokens=None):
    """
    Returns the largest item in the stream

    >>> from streamutils import *
    >>> dates = ['2014-01-01', '2014-02-01', '2014-03-01']
    >>> head(tokens=dates) | smax()
    '2014-03-01'

    :param key: See documentation for :py:func:`max`
    :param tokens: a list of things
    :return: The largest item in the stream (as defined by python :py:func:`max`)
    """
    return max(tokens, key=key) if key else max(tokens)

@terminator
def smin(key=None, tokens=None):
    """
    Returns the smallest item in the stream

    >>> from streamutils import *
    >>> dates = ['2014-01-01', '2014-02-01', '2014-03-01']
    >>> head(tokens=dates) | smin()
    '2014-01-01'

    :param key: See documentation for :py:func:`min`
    :param tokens: a list of things
    :return: The largest item in the stream (as defined by python :py:func:`min`)
    """
    return min(tokens, key=key) if key else min(tokens)

@terminator
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

@terminator
def ssum(start=0, tokens=None):
    """
    Adds the items that pass through the stream via call to :py:func:`sum`
    
    >>> from streamutils import *
    >>> head(tokens=[1,2,3]) | ssum()
    6

    :param start: Initial value to start the sum, returned if the stream is empty
    :return: sum of all the values in the stream
    """
    return sum(tokens, start)

@terminator
def sumby(keys=None, values=None, tokens=None):
    """
    If keys and values are not set, given a series of key, value items, returns a ``dict`` of summed values, grouped by key
    
    >>> from streamutils import *
    >>> sums = head(tokens=[('A', 2), ('B', 6), ('A', 3), ('C', 20), ('C', 10), ('C', 30)]) | sumby()
    >>> sums == {'A': 5, 'B': 6, 'C': 60}
    True

    If keys and values are set, given a series of dicts, return a dict of dicts of summed values, grouped by
    a tuple of the indicated keys. 
    
    >>> from streamutils import *
    >>> data=[]
    >>> data.append({'Region': 'North', 'Revenue': 4, 'Cost': 8})
    >>> data.append({'Region': 'North', 'Revenue': 3, 'Cost': 2})
    >>> data.append({'Region': 'West', 'Revenue': 6, 'Cost': 3})
    >>> sums = head(tokens=data) | sumby(keys='Region', values=['Revenue', 'Cost'])
    >>> sums == {'North': {'Revenue': 7, 'Cost': 10}, 'West': {'Revenue': 6, 'Cost': 3}}
    True

    :return: dict mapping each key to the sum of all the values corresponding to that key
    """
    result={}
    if keys and values:
        for data in tokens:
            aggkey= data[keys] if isinstance(keys, string_types) else tuple(data[key] for key in _wrapInIterable(keys))
            for value in _wrapInIterable(values):
                result.setdefault(aggkey, {})[value]=result.get(aggkey, {}).get(value, 0)+data[value]
    else:
        for (key, value) in tokens:
            result[key]=result.get(key, 0)+value
    return result

@terminator
def meanby(keys=None, values=None, tokens=None):
    """
    If key is not set, given a series of key, value items, returns a dict of means, grouped by key
    If keys is set, given a series of ``dict``s, returns the mean of the values grouped by
    a tuple of the values corresponding to the keys

    >>> from streamutils import *
    >>> means = head(tokens=[('A', 2), ('B', 6), ('A', 3), ('C', 20), ('C', 10), ('C', 30)]) | meanby()
    >>> means == {'A': 2.5, 'B': 6, 'C': 20}
    True

    >>> from streamutils import *
    >>> means = head(tokens=[{'key': 1, 'value': 2}, {'key': 1, 'value': 4}, {'key': 2, 'value': 5}]) | meanby('key', 'value')
    >>> means == {1: {'value': 3.0}, 2: {'value': 5.0}}
    True

    :param: keys ``dict`` keys for the values to aggregate on
    :params: values ``dict`` keys for the values to be aggregated
    :return: dict mapping each key to the sum of all the values corresponding to that key
    """
    counts={}
    totals={}
    if keys and values:
        values=_wrapInIterable(values)
        for data in tokens:
            aggkey=data[keys] if isinstance(keys, string_types) else tuple(data[key] for key in _wrapInIterable(keys))
            for value in values:
                counts[aggkey]=counts.get(aggkey, 0)+1
                totals.setdefault(aggkey, {})[value]=totals.get(aggkey, {}).get(value, 0)+data[value]
        return dict((key, dict((value, totals[key][value]/counts[key]) for value in values)) for key in totals)
    else:
        for (key, value) in tokens:
            counts[key]=counts.get(key, 0)+1
            totals[key]=totals.get(key, 0)+value
        return dict((key, totals[key]/counts[key]) for key in counts)

@terminator
def firstby(keys=None, values=None, tokens=None):
    """
    Given a series of key, value items, returns a dict of the first value assigned to each key

    >>> from streamutils import *
    >>> firsts = [('A', 2), ('B', 6), ('A', 3), ('C', 20), ('C', 10), ('C', 30)] | firstby()
    >>> firsts == {'A': 2, 'B': 6, 'C': 20}
    True
    >>> firsts = [{'key': 'A', 'value': 2}, {'key': 'B', 'value': 6}, {'key': 'A', 'value': 3}, {'key': 'C', 'value': 20}, {'key': 'C', 'value': 10}] | firstby(keys='key', values='value')
    >>> firsts == {'A': {'value': 2}, 'B': {'value': 6}, 'C': {'value': 20}}
    True

    :param: keys ``dict`` keys for the values to aggregate on
    :params: values ``dict`` keys for the values to be aggregated
    :return: dict mapping each key to the first value corresponding to that key
    """
    result={}
    if keys and values:
        for data in tokens:
            aggkey= data[keys] if isinstance(keys, string_types) else tuple(data[key] for key in _wrapInIterable(keys))
            for value in _wrapInIterable(values):
                if aggkey not in result:
                    result.setdefault(aggkey, {})[value]=data[value]
    else:
        for (key, value) in tokens:
            if key not in result:
                result[key]=value
    return result

@terminator
def lastby(keys=None, values=None, tokens=None):
    """
    Given a series of key, value items, returns a dict of the last value assigned to each key

    >>> from streamutils import *
    >>> lasts = head(tokens=[('A', 2), ('B', 6), ('A', 3), ('C', 20), ('C', 10), ('C', 30)]) | lastby()
    >>> lasts == {'A': 3, 'B': 6, 'C': 30}
    True

    :return: dict mapping each key to the last value corresponding to that key
    """
    result={}
    if keys and values:
        for data in tokens:
            aggkey=data[keys] if isinstance(keys, string_types) else tuple(data[key] for key in _wrapInIterable(keys))
            for value in _wrapInIterable(values):
                result.setdefault(aggkey, {})[value]=data[value]
    else:
        for (key, value) in tokens:
            result[key]=value
    return result

@terminator
def countby(keys, tokens=None):
    """
    Given a series of keys, return a dict of how many times each corresponding set of values appear in the stream

    >>> counts = [{'A': 6}, {'A': 5}, {'A': 4}] | countby(keys='A')
    >>> dict(counts) == {6: 1, 5: 1, 4: 1}
    True
    """
    return tokens | smap(lambda x: x[keys if isinstance(keys, string_types) else tuple(data[key] for key in keys)]) | bag()

@terminator
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

@terminator
def action(func, tokens=None):
    """
    Calls a function for every element that passes through the stream. Similar to ``smap``, only ``action`` is a ``Terminator`` so will
    end the stream

    >>> ['Hello', 'World'] | smap(str.upper) | action(print)
    HELLO
    WORLD

    :param func: function to call
    :param tokens: a list of things
    """
    for line in tokens:
        func(line)

@terminator
def sreduce(func, initial=None, tokens=None):
    """
    Uses a function to :py:func:`reduce` the output to a single value

    :param func: Function to use in the reduction
    :param initial: An initial value
    :return: Output of the reduction
    """
    return reduce(func, tokens, initial)

@terminator
def write(fname=None, mode='wt', encoding=None, tokens=None):
    r"""
    Writes the output of the stream to a file, or via ``print`` if no file is supplied. Calls to ``print`` include
    a call to :py:func:`str.rstrip` to remove trailing newlines. ``mode`` is only used if ``fname`` is a string

    >>> from streamutils import *
    >>> from six import StringIO
    >>> lines=['%s\n' % line for line in ['Three', 'Blind', 'Mice']]
    >>> lines | head() | write() # By default prints to the console
    Three
    Blind
    Mice
    >>> buffer = StringIO() # Alternatively write to an open filelike object
    >>> lines | head() | write(fname=buffer)
    >>> writtenlines=buffer.getvalue().splitlines()
    >>> writtenlines[0]=='Three'
    True

    :param fname: If `str`, filename to write to, otherwise open file-like object to write to. Default of `None` implies
                    write to standard output
    :param mode: The mode to use to open ``fname`` (default of 'wt' as per :py:func:`io.open`)
    :param encoding: Encoding to use to write to the file
    :param tokens: Lines to write to the file
    """
    if not fname:
        for line in tokens:
            print(line.rstrip() if isinstance(line, string_types) else line)
    elif isinstance(fname, string_types):
        with open(fname, encoding=encoding, mode=mode) as f:
            f.writelines(tokens)
    elif hasattr(fname, 'writelines'):
        fname.writelines(tokens)
    elif hasattr(fname, 'write'):
        for line in tokens:
            fname.write(line)
    else:
        raise TypeError('fname must be a filename or a file-like thing, got %s which is a %s' % (fname, type(fname)))

@connector
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

@connector
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
        with _eopen(name, encoding) if fname else _noopcontext(name) as tokens: #in the else case, name is actually the tokens originally passed
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

@connector
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
    :param tokens: Stream of tokens to take the last few members of (i.e. not a list of filenames to take the last few lines of)
    :return: A list of the last ``n`` items
    """
    with _eopen(fname, encoding) if fname else _noopcontext(tokens) as tokens:
        return deque(tokens, n)

@connector
def sslice(start=1, stop=None, step=1, fname=None, encoding=None, tokens=None):
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
    :param stop: Maximum token to return (default: None implies read to the end)
    :param step: Interval between tokens
    :param fname: Filename to use as input
    :param encoding: Unicode encoding to use to open files
    :param tokens: list of filenames to open
    """
    with _eopen(fname, encoding) if fname else _noopcontext(tokens) as tokens:
        for line in islice(tokens, start-1, stop-1 if stop else None, step):
            yield line  # Can't return the iterator or the file will be closed (I think!)

@connector
def follow(fname, encoding=None): #pragma: no cover - runs forever!
    """
    Monitor a file, reading new lines as they are added (equivalent of `tail -f` on UNIX). (Note: Never returns)

    :param fname: File to read
    :param encoding: encoding to use to read the file
    """
    with _eopen(fname, encoding) as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            yield line

@connector
def csvread(fname=None, encoding=None, dialect='excel', n=0, names=None, skip=0, restkey=None, restval=None, tokens=None, **fmtparams):
    """
    Reads a file or stream and parses it as a csv file using a :py:func:`csv.reader`. If names is set, uses a :py:func:`csv.DictReader`

    >>> from streamutils import *
    >>> data=[]
    >>> data.append('Region;Revenue;Cost')
    >>> data.append('North;10;5')
    >>> data.append('West;15;7')
    >>> csvread(delimiter=';', skip=1, tokens=data) | smap(lambda x: int(x[1])) | ssum()
    25
    >>> csvread(delimiter=';', skip=1, names=['Region', 'Revenue', 'Cost'], tokens=data) | smap(lambda x: int(x['Cost'])) | ssum()
    12
    >>> csvread(delimiter=';', skip=1, n=1, tokens=data) | unique() | write()
    North
    West

    :param fname: filename to read from - if None, reads from the stream
    :param encoding: encoding to use to read the file (warning: the csv module in python 2 does not support unicode 
        encoding - if you run into trouble I suggest reading the file with ``read`` then passing the output through the 
        ``unidecode`` library using ``smap`` before ``csvread``)
    :param dialect: the csv dialect (see :py:func:`csv.reader`)
    :param n: the columns to return (starting at 1). If set, names defines the names for these columns, not the names for all columns
    :param names: the keys to use in the DictReader (see the fieldnames keyword arg of :py:func:`csv.DictReader`)
    :param skip: rows to skip (e.g. header rows) before reading data
    :param restkey: (see the restkey keyword arg of :py:func:`csv.DictReader`)
    :param restval: (see the restval keyword arg of :py:func:`csv.DictReader`)
    :param fmtparams: see :py:func:`csv.reader`
    """
    import csv
    with _eopen(fname, encoding) if fname else _noopcontext(tokens) as f:
        reader = csv.reader(islice(f, skip, None), dialect, **fmtparams) if (n or not names) else csv.DictReader(islice(f, skip, None), names, restkey, restval, dialect, **fmtparams)
        for row in reader:
            if n:
                yield _ntodict(row, n, names)
            else:
                yield row

@terminator
def csvwrite(fname=None, mode='wb', encoding=None, dialect='excel', names=None, restval='', extrasaction='raise', tokens=None, **fmtparams):
    """
    Writes the stream to a file (or stdout) in csv format using :py:func:`csv.writer`. If names is set, uses a :py:func:`csv.DictWriter`

    >>> [{'Region': 'North', 'Revenue': 5, 'Cost' : 3}, {'Region': 'West', 'Revenue': 15, 'Cost' : 7}] | csvwrite(delimiter=';', names=['Region', 'Revenue', 'Cost']) # doctest: +NORMALIZE_WHITESPACE
    Region;Revenue;Cost
    North;5;3
    West;15;7
    >>> [['Region', 'Revenue', 'Cost'], ['North', 5, 3], ['West', 15, 7]] | csvwrite() # doctest: +NORMALIZE_WHITESPACE
    Region,Revenue,Cost
    North,5,3
    West,15,7

    :param fname: filename or file-like object to write to - if None, uses stdout
    :param encoding: encoding to use to write the file
    :param names: the keys to use in the DictWriter
    """
    import csv

    with open(fname, mode=mode, encoding=encoding) if fname and isinstance(fname, string_types) else _noopcontext(fname) if fname else _noopcontext(sys.stdout) as f:
        if names:
            writer=csv.DictWriter(f, fieldnames=names, restval=restval, extrasaction=extrasaction, **fmtparams)
            if not PY3 and sys.version_info[1]==6: # pragma: no cover
                writer.writerow(dict((name, name) for name in names))
            else:
                writer.writeheader()
        else:
            writer=csv.writer(f, dialect=dialect, **fmtparams)
        for token in tokens: 
            writer.writerow(token)

@connector
def bzread(fname=None, encoding=None, tokens=None):
    """
    Read a file or files from bzip2-ed archives and output the lines within the files.

    >>> find('examples/NASA*.bz2') | bzread() | head(1) | write()
    199.72.81.55 - - [01/Jul/1995:00:00:01 -0400] "GET /history/apollo/ HTTP/1.0" 200 6245

    :param fname:  filename or ``list`` of filenames
    :param encoding: unicode encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames
    """
    files=_wrapInIterable(fname) if fname else tokens
    openfunc=bz2.BZ2File if not PY3 or sys.version_info.minor<3 else bz2.open
    for name in files:
        with _wrappedopen(openfunc, name, encoding=encoding) as lines:
            for line in lines:
                yield line

@connector
def gzread(fname=None, encoding=None, tokens=None):
    """
    Read a file or files from gzip-ed archives and output the lines within the files.

    :param fname:  filename or ``list`` of filenames
    :param encoding: unicode encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames
    """
    files=_wrapInIterable(fname) if fname else tokens
    if files is None:  #pragma: no cover
        raise ValueError('No filename or stream supplied')
    for name in files:
        with _wrappedopen(gzip.open, name, encoding=encoding) as lines:
            for line in lines:
                yield line

@connector
def read(fname=None, encoding=None, skip=0, tokens=None):
    """
    Read a file or files and output the lines it contains. Files are opened with :py:func:`io.read`

    >>> from streamutils import *
    >>> read('https://raw.github.com/maxgrenderjones/streamutils/master/README.md') | search('^[-] Source Code: (.*)', 1) | write()
    http://github.com/maxgrenderjones/streamutils

    :param fname: filename or ``list`` of filenames. Can either be paths to local files or URLs (e.g. http:// or ftp:// - supports the same protocols as :py:func:`urllib2.urlopen`)
    :param encoding: encoding to use to open the file (if None, use platform default)
    :param skip: number of lines to skip at the beginning of each file
    :param tokens: list of filenames
    """
    if fname or tokens:
        files=_wrapInIterable(fname) if fname else tokens
        for name in files:
            with _eopen(name, encoding) as f:
                for line in islice(f, skip, None):
                    yield line
    else:  #pragma: no cover
        import fileinput
        for line in fileinput.input('-'):
            yield line

@connector
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
    :param match: If ``False`` (default) use :py:func:`re.search` elif ``True`` use :py:func:`re.match`
    :param fname: Filename (or list of flienames) to search through
    :param encoding: Encoding to use to open the files
    :param names: dict of groups to names - if included, result will be a dict
    :param inject: Used in conjunction with names, a ``dict`` of key: values to inject into the results dictionary
    :param strict: If True, raise a ValueError if every line doesn't match the pattern (default False)
    :param flags: Regexp flags to use
    :param tokens: strings to search through
    """
    matcher=re.compile(pattern) if not flags else re.compile(pattern, flags=flags)
    if fname is not None:
        tokens=read(fname, encoding)
    for line in tokens:
        result=matcher.match(line) if match else matcher.search(line)
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

@connector
def replace(old, new, tokens=None):
    """
    Replace ``old`` in each tokens with ``new`` via call to ``.replace`` on each token (e.g. :py:func:`str.replace`)

    :param old: text to replace
    :param new: what to replace it with
    :param tokens: typically a series of strings
    """
    for line in tokens:
        yield line.replace(old, new)

@connector
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
        result=matcher.match(line) if match else matcher.search(line)
        if result and not v:
            yield line
        elif v and not result:
            yield line
@connector
def nomatch(pattern, match=False, flags=0, tokens=None):
    """
    Filters the input for strings that don't match the pattern (think UNIX ``grep -v``)

    >>> import re
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

@connector
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


    :param str pathpattern: Pattern to match (caution - ``/`` or ``os.sep`` is not special)
    :param bool matchcase: Whether to match case-senitive on case-insensitive file systems
    :param tokens: list of filename strings to match
    """
    import fnmatch
    for line in tokens:
        line.replace(os.sep, '/')
        if matchcase and fnmatch.fnmatchcase(line, pathpattern):
            yield line
        elif not matchcase and fnmatch.fnmatch(line, pathpattern):
            yield line
@connector
def find(pathpattern=None, tokens=None):
    """
    Searches for files the match a given pattern. For example

    >>> import os
    >>> from streamutils import find, replace, write
    >>> find('src/version.py') | replace(os.sep, '/') | write()    #Only searches src directory
    >>> find('src/*/version.py') | replace(os.sep, '/') | write()  #Searches full directory tree
    src/streamutils/version.py

    :param str pathpattern: :py:func:`glob.glob`-style pattern
    :param tokens: A list of ``glob``-style patterns to search for
    :return: An iterator across the filenames found by the function
    """
    paths=_wrapInIterable(pathpattern) if pathpattern else tokens
    if paths:
        return ichain.from_iterable(glob.iglob(path) for path in paths)
    else:
        return glob.iglob('**/*')

@connector
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
    :type n: int or list
    :param str word: a pattern that will be used to select words using :py:func:`re.findall` - (default \S+)
    :param str outsep: a string separator to join together the words that are found into a new string (or None to output a list of words)
    :param names: (Optional) a name or list of names of the n extracted words, used to construct a dict to be passed down the pipeline
    :type names: str or list
    :param dict inject: For use with ``names`` - extra key/value pairs to include in the output dict
    :param flags: flags to pass to the re engine to compile the pattern
    :param tokens: list of tokens to iterate through in the function (usually supplied by the previous function in the pipeline)
    :raise: ``ValueError`` if there are less than n (or max(n)) words in the string
    """
    matcher=re.compile(word) if not flags else re.compile(word, flags=flags)
    for line in tokens:
        result=matcher.findall(line)
        yield _ntodict(result, n, names, inject) if not outsep else outsep.join(_ntodict(result, n, names, inject))

@connector
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
    for line in tokens:
        result=line.split(sep)
        yield _ntodict(result, n, names, inject) if not outsep else outsep.join(_ntodict(result, n, names, inject))
@connector
def join(sep=' ', tokens=None):
    r"""
    Joins a list-like thing together using the supplied `sep` (think :py:func:`str.join`). Defaults to joining with a space

    >>> split(sep=',', n=[1,4], tokens=['flopsy,mopsy,cottontail,peter']) | join(',') | write()
    flopsy,peter

    :param sep: string separator to use to join each line in the stream (default ' ')
    """
    for line in tokens:
        yield sep.join(line)

@connector
def update(values=None, funcs=None, tokens=None):
    """
    For each ``dict`` token in the stream, updates it with a ``values`` ``dict``, then updates it with ``funcs``, a ``dict`` mapping of ``key`` to ``func``
    which it uses to set the value of ``key`` to ``func(token)``. A bit like ``convert``, only it's designed to let you add keys, not just modify existing ones.
    Currently modifies the ``dict``s in the stream (i.e. not pure), but this should not be relied on - in the future it may yield (shallow) copied ``dict``s in
    order to be pure (at a cost of more allocations)

    >>> from streamutils import *
    >>> lines=[{'first': 'Jack', 'last': 'Bauer'}, {'first': 'Michelle', 'last': 'Dessler'}]
    >>> for actor in update(funcs={'initials': lambda x: x['first'][0]+x['last'][0]}, tokens=lines):
    ...     print(actor['initials'])
    JB
    MD
    >>> for actor in update(values={'Show': '24'}, tokens=lines):
    ...     print(actor['Show'])
    24
    24

    :param values: ``dict`` 
    :param funcs: ``dict`` of ``key``: ``function``s
    :param tokens: a stream of ``dict``s

    """
    for d in tokens:
        if values:
            d.update(values)
        if funcs:
            for key, func in funcs.items():
                d[key]=func(d)
        yield d

@connector
def convert(converters, defaults={}, tokens=None):
    """
    Takes a ``dict`` or ``list`` of tokens and calls the supplied converter functions. 
    If a ``ValueError`` is thrown, sets the field to the default for that field if supplied, otherwise reraises.

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

@connector
def smap(*funcs, **kwargs): #python 3.x will let you write smap(*funcs, tokens=None), but 2.x won't
    """
    Applies a transformation function to each element of the stream (or series of function). Note that `smap(f, g, tokens)` yields `f(g(token))`

    >>> from streamutils import *
    >>> smap(str.upper, tokens=['aeiou']) | write()
    AEIOU
    >>> smap(str.upper, str.strip, str.lower, tokens=[' hello ', ' world ']) | write()
    HELLO
    WORLD

    :param *funcs: functions to apply
    :param tokens: list/iterable of objects
    """
    return map(reduce(lambda f, g: lambda x: f(g(x)), funcs), kwargs['tokens'])

@connector
def strip(chars=None, tokens=None):
    r"""
    Runs ``.strip`` against each line of the stream

    >>> from streamutils import *
    >>> line=strip(tokens=['  line\n']) | first()
    >>> line=='line'
    True

    :param tokens: A series of lines to remove whitespace from
    """
    return map(lambda x: x.strip(chars), tokens)

@connector
def sfilter(func=None, tokens=None):
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
    return filter(func, tokens)

@connector
def sfilterfalse(func=None, tokens=None):
    """
    Passes through items for which the output of the filter function is False in a boolean context

    >>> sfilterfalse(lambda x: x.endswith('ball'), tokens=['football', 'rugby', 'tennis', 'volleyball']) | write()
    rugby
    tennis

    :param filterfunction: Function to use for filtering
    :param tokens: List of things to filter
    """
    return filterfalse(func, tokens)

@connector
def takewhile(func=None, tokens=None):
	"""
	Passes through items until the supplied function returns False (Equivalent of :py:func:`itertools.takewhile`)

	>>> [1,2,3,2,1] | takewhile(lambda x: x<3) | aslist()
	[1, 2]

	:param func: The function to use as a predicate
	:param tokens: List of things to filter
	"""
	return itakewhile(func, tokens)

@connector
def dropwhile(func=None, tokens=None):
	"""
	Passes through items until the supplied function returns False (Equivalent of :py:func:`itertools.dropwhile`)

	>>> [1,2,3,2,1] | dropwhile(lambda x: x<3) | aslist()
	[3, 2, 1]

	:param func: The function to use as a predicate
	:param tokens: List of things to filter
	"""
	return idropwhile(func, tokens)

@connector
def unwrap(tokens=None):
    """
    Yields a stream of ``list``s, with one level of nesting in the tokens the stream unwrapped (if present).

    >>> [[[1], [2]], [[2, 3, 4], [5]], [[[6]]]] | unwrap() | write()
    [1, 2]
    [2, 3, 4, 5]
    [[6]]

    :param tokens: a stream of `Iterable`s
    """
    for token in tokens:
        yield list(ichain.from_iterable(token))

@connector
def traverse(tokens=None):
    r"""
    Performs a full depth-first unwrapping of the supplied tokens. Strings are **not** unwrapped

    >>> ["hello", ["hello", [["world"]]]] | traverse() | join() | write()
    hello
    hello world

    :param tokens: a stream of ``Iterables`` to be unwrapped
    """
    def recunwrap(token):
        if isinstance(token, string_types) or not isinstance(token, Iterable):
            yield token
        else:
            for subtoken in _wrapInIterable(token):
                for subsubtoken in recunwrap(subtoken):
                    yield subsubtoken
    for token in tokens:
        yield list(recunwrap(token))

@connector
def separate(tokens=None):
    r"""
    Takes a stream of ``Iterable``s, and yields items from the iterables 

    >>> [["hello", "there"], ["how", "are"], ["you"]] | separate() | write()
    hello
    there
    how
    are
    you

    :param tokens: a stream of Iterables
    """
    for token in ichain.from_iterable(tokens):
        yield token

@connector
def combine(func=None, tokens=None):
    r"""
    Given a stream, combines the tokens together into a ``list``. If ``func`` is not ``None``, the ``tokens`` are combined 
    into a series of ``list``s, chopping the ``list`` every time ``func`` returns ``True``

    >>> ["1 2 3", "4 5 6"] | words() | separate() | smap(lambda x: int(x)+1) | combine() | write()
    [2, 3, 4, 5, 6, 7]
    >>> ["first", "line\n", "second", "line\n", "third line\n"] | combine(lambda x: x.endswith('\n')) | join(' ') | write()
    first line
    second line
    third line
    
    Note that `separate` followed by `combine` is not a no-op.

    >>> [["hello", "small"], ["world"]] | separate() | combine() | join() | write()
    hello small world

    :param func: If not `None` (the default), combine until `func` returns `True`
    :param tokens: a stream of things
    """
    if func is None:
        yield list(tokens)
    else:
        agg=[]
        for token in tokens:
            agg.append(token)
            if func(token):
                yield agg
                agg=[]
        if agg:
            yield agg

@connector
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
        else:  # pragma: no cover
            raise TypeError('Format expects a sequence or a mapping - got a %s' % type(token))
