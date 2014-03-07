#!/usr/bin/env python
# coding: utf-8
# vim: set tabstop=4 shiftwidth=4 expandtab:
"""
Implementation of bash style function piping
Some implementation details from http://www.dabeaz.com/generators/
"""

from __future__ import unicode_literals, print_function, division

from six import StringIO, string_types, integer_types, MAXSIZE, PY3
from six.moves import reduce, filter, filterfalse, zip   # These work - moves is a fake module
from six.moves.urllib.parse import urlparse
from six.moves.urllib.request import urlopen

import re, time, subprocess, os, glob, locale, shlex, sys, codecs

from io import open, TextIOWrapper
from contextlib import closing

from collections import Iterable, Callable, Iterator, deque, Mapping, Sequence
try:
    from collections import OrderedDict, Counter
except ImportError:
    from ordereddict import OrderedDict #To use OrderedDict backport
    from counter import Counter         #To use Counter backport
from itertools import chain, islice
from itertools import count as icount
from functools import update_wrapper

__author__= 'maxgrenderjones'
__docformat__ = 'restructuredtext'

class SHWrapper(object):
    def __getattribute__(self, name):
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

    def __init__(self, func, tokenskw):

        """
        Creates a composable function by wrapping func, which expects to receive tokens on its tokenskw
        :param func:
        :param tokenskw:
        """
        self.func=func
        self.tokenskw=tokenskw


    def __call__(self, *args, **kwargs):
        #print 'Calling via ConnectingGenerator'
        return ConnectingGenerator(self.func, self.tokenskw, args, kwargs)
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

    def __iter__(self):
        it=self.func(*self.args, **self.kwargs)
        if isinstance(it, Iterator):
            return it # Function returned a genarator (or similar)
        elif isinstance(it, Iterable):
            return it.__iter__() #Function returned a list (or similar)
        elif hasattr(it, '__iter__'):
            return it.__iter__() #Function returned an iterable duck
        elif str(type(it)) in ("<class 'pbs.RunningCommand'>"): #can't compare directly in case this feature not installed
            return iter(it.stdout.splitlines()) #stdout is a string, not an open file
        else:
            print(dir(it))
            raise TypeError('Composable Functions must return Iterators or Iterables (got %s)' % type(iter))

    def __or__(self, other):
        #print 'OR being run for %s with pattern %s' % (self.func.__name__, self.args[0])
        if isinstance(other, ConnectingGenerator):
            #print('Connecting output of %s to the tokens of %s' % (self.func.__name__, other.func.__name__))
            other.kwargs[other.tokenskw]=self
            return other
        elif isinstance(other, Terminator):
            other.kwargs[other.tokenskw]=self
            return other.func(*other.args, **other.kwargs)
            #@Todo Call close() back down the chain rather than waiting for GC to do it for us
        else:
            raise TypeError('The ConnectingGenerator is being composed with a %s' % type(other))

    def __getattr__(self, name):
        return getattr(self.func, name)

class Terminator(Callable):
    def __init__(self, func, tokenskw):
        #print('Create a terminating function by wrapping %s which takes tokens as "%s"' % (func.__name__, tokenskw))
        self.func=func
        self.tokenskw=tokenskw
        #self.__doc__=func.__doc__ #makes docstrings work

    # @property
    # def __doc__(self):
    #     return self.func.__doc__ if self.func else 'Doc for a Terminator'
    #
    # @property
    # def __name__(self):
    #     return self.func.__name__ if self.func else 'Terminator'

    def __call__(self, *args, **kwargs):
        self.args=args
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
        if PY3 and sys.version_info.minor>2:
            return TextIOWrapper(urlopen(fname), encoding=encoding)
        else:
            # This should be universal new-line wrapped, but there are two bugs
            # in python whereby TextIOWrapper doesn't play nice with urlopen that were fixed
            # in python 3.3 @TODO wrap output of urlopen with unicode and newline support
            reader=codecs.getreader(encoding or locale.getpreferredencoding())
            return reader(urlopen(fname))
    else:
        if not encoding:
            encoding=head(tokens=open(fname), n=2) | search(r'coding[:=]\s*"?([-\w.]+)"?', 1) | first()
        if encoding:
            #print('Opening file %s with encoding %s' % (fname, encoding))
            return open(fname, encoding=encoding)
        else:
            return open(fname)

def _gettokens(fname, encoding=None, tokens=None):
    if fname:
        return _eopen(fname, encoding)
    elif tokens is not None:
        if not isinstance(tokens, Iterator):
            return iter(tokens)
        else:
            return tokens
    else:
        raise ValueError('Either fname or tokens must be set')

def _groupstodict(match, group, names, inject={}):
    """

    :param match: a Match Object
    :param group: An integer group to return or a list of groups
    :param names: A dict of groups to dict keys used to form a dict to return
    :param inject: Extra key value pairs to inject into the returned dict
    :return:
    """
    if isinstance(group, integer_types):
        if names:
            d= OrderedDict((names[group], match.group(group)))
            if inject:
                d.update(inject)
            return d
        else:
            return match.group(group)
    else:
        if names:
            if isinstance(names, Mapping):
                d= OrderedDict((names[g], match.group(g)) for g in (group if group else names))
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

    :param results: an list containing the results of a ``.split`` or ``.findall`` operation
    :param group: An integer group to return or a list of groups
    :param names: A dict of groups to dict keys used to form a dict to return
    :param inject: Extra key value pairs to inject into the returned dict
    :return:
    """
    if isinstance(n, integer_types) and n>0:
        if n>0 and n>len(results):
            raise ValueError('Not enough items in list %s to pick item %d' % (results, n))
        if names:
            d= OrderedDict((names[n], results[n-1]))
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


def wrap(func, tokenskw='tokens'):
    '''
    Decorator function used to create a ComposableFunction

    :param func: The function to be wrapped - should either yield items into the pipeline or return an iterable
    :param tokenskw: The keyword argument that func expects to receive tokens on
    '''
    cf = ComposableFunction(func, tokenskw)
    #I'm pretty sure newf = update_wrapper(newf, func) ought to work, but it doesn't. I'd love to know why
    cf = update_wrapper(cf, func)
    __test__[func.__name__]=func
    return cf

def wrapTerminator(func, tokenskw='tokens'):
    """
    Used as a decorator to create a Terminator function that can end a pipeline

    :param func: The function to be wrapped - should return the desired output of the pipeline
    :param tokenskw: The keyword argument that func expects to receive tokens on
    :return: A Terminator function
    """
    t = Terminator(func, tokenskw)
    # t.__doc__ = func.__doc__
    # t.__name__ = func.__name__
    t = update_wrapper(t, func)
    __test__[func.__name__]=func
    return t

def wrapInIterable(item):
    if item is None:
        return None
    elif isinstance(item, integer_types) or isinstance(item, string_types):
        return [item]
    elif isinstance(item, Iterable):
        return item
    elif hasattr(item, '__iter__'):
        return item
    else:
        return [item]

@wrap
def run(args, err=False, cwd=None, env=None, tokens=None, ):
    stdin=None if tokens is None else StringIO("".join(list(tokens)))
    if isinstance(args, string_types):
        args=shlex.split(args)
    if not err:
        output=subprocess.check_output(args, cwd=cwd, stdin=stdin)
    else:
        output=subprocess.check_output(args, cwd=cwd, stderr=subprocess.STDOUT, stdin=stdin)
    encoding=locale.getdefaultlocale()[1]
    for line in StringIO(output.decode(encoding)):
        if os.linesep!='\n' and line.endswith(os.linesep):
            yield line[:-len(os.linesep)]
        else:
            yield line


@wrapTerminator
def first(default=None, tokens=None):
    for line in tokens:
        return line
    return default

@wrapTerminator
def last(default=None, tokens=None,):
    out=default
    for line in tokens:
        out=line
    return out


@wrapTerminator
def aslist(tokens=None):
    """
    Returns the output of the stream as a list

    :param tokens: Iterable object providing tokens (set by the pipeline)
    :return: a ``list`` containing all the tokens in the pipeline
    """
    return list(tokens)

@wrapTerminator
def nth(n, default=None, tokens=None):
    """
    Returns the nth item in the stream, or a default if the list has less than n items

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
    Sorts the output of the stream (see documentation for py:func:`sorted`). Warning: ``cmp`` was removed from ``sorted``
    in python 3

    >>> from streamutils import *
    >>> for line in (find('*.py') | replace(os.sep, '/') | ssorted()):
    ...     print(line)
    ez_setup.py
    setup.py

    """
    if tokens:
        if PY3:
            return sorted(tokens, key=key, reverse=reverse)
        else:
            return sorted(tokens, cmp, key, reverse)
    else:
        return tokens

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
def ssum(tokens=None):
    """
    Adds the items that pass through the stream
    """
    return sum(tokens)

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
    """
    Writes the output of the stream to a file, or via ``print`` if no file is supplied. Calls to ``print`` include
    a call to :py:func:`str.rstrip` to remove trailing newlines

    :param fname: If `str`, filename to write to, otherwise open file-like object to write to. Default of `None` implies
                    write to standard output
    :param encoding: Encoding to use to write to the file
    :param tokens: Lines to write to teh file
    """
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

    :param n: Number of lines to return (0=all lines) or a list of lines to return
    :param fname: Filename to open
    :param skip: Number of lines to skip before returning lines
    :param encoding: Encoding of file to open. If None, will try to guess the encoding based on coding= strings
    :param tokens: Either set by the pipeline or provided as an initial list of items to pass through the pipeline
    """
    try:
        tokens=_gettokens(fname, encoding, tokens)
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

    :param n: How many items to return e.g. ``n=5`` will return 5 items
    :param fname: A filename from which to read the last ``n`` items (10 by default)
    :param encoding: The enocding of the file
    :param tokens: Will be set by the chain
    :return: A list of the last ``n`` items
    """
    try:
        tokens=_gettokens(fname, encoding, tokens)
        if tokens is not None:
            return deque(tokens, n)
        else:
            ValueError('Either fname or tokens must be set')
    finally:
        if fname and tokens:
            tokens.close()

@wrap
def sslice(start=0, stop=MAXSIZE, step=1, fname=None, encoding=None, tokens=None):
    """

    :param start:
    :param stop:
    :param step:
    :param fname:
    :param encoding:
    :param tokens:
    """
    try:
        tokens=_gettokens(fname, encoding, tokens)
        for line in islice(tokens, start, stop, step):
            yield line
    finally:
        if fname and tokens:
            tokens.close()

@wrap
def follow(fname, encoding=None):
    f = _eopen(fname, encoding)
    f.seek(0, os.SEEK_END)
    while True:
        line = f.readline()
        if not line:
            time.sleep(1)
            continue
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
        files=wrapInIterable(fname) if fname else tokens
        for name in files:
            with _eopen(name, encoding) as f:
                for line in f:
                    #print 'Cat: %s' % line.strip()
                    yield line
    else:
        import fileinput
        for line in fileinput.input('-'):
            yield line

@wrap
def search(pattern, group=0, to=None, match=False, fname=None, encoding=None, names=None, flags=0, tokens=None):
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
    :param flags: Regexp flags to use
    :param tokens: strings to search through
    """
    matcher = re.compile(pattern) if not flags else re.compile(pattern, flags=flags)
    if fname is not None:
        tokens=read(fname, encoding)
    for line in tokens:
        if to:
            if match:
                if matcher.match(line):
                    yield matcher.sub(to, line)
            else:
                yield matcher.sub(to, line)
        else:
            result = matcher.match(line) if match else matcher.search(line)
            if result:
                yield _groupstodict(result, group, names)

@wrap
def replace(text, replacement, tokens=None):
    """
    Replace ``text`` in the tokens with ``replacement`` via ``.replace`` (i.e. :py:func:`str.replace`)

    :param text: text to replace
    :param replacement: what to replace it with
    :param tokens: series of strings
    """
    for line in tokens:
        yield line.replace(text, replacement)

@wrap
def matches(pattern, match=False, flags=0, v=False, tokens=None):
    """
    Filters the input for strings that match the pattern (think UNIX ``grep``)

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
    Filter tokens for strings that match the pathpattern using :py:func:`fnmatch.fnmatch` or :py:func:`fnmatch.fnmatchcase`
    ``os.sep`` (i.e. ``\\`` on windows) will be replaced with ``/`` to allow ``/`` to be used in the pattern

    >>> from streamutils import *
    >>> lines = ['setup.py', 'README.md', 'streamutils/__init__.py']
    >>> fnmatches('*.py', False, lines) | write()
    setup.py
    streamutils/__init__.py
    >>> fnmatches('*/*.py', False, lines) | write()
    streamutils/__init__.py

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

    :param pathpattern: ``glob``-style pattern
    :param tokens: A list of ``glob``-style patterns to search for
    :return: An iterator across the files found by the function
    """
    if pathpattern:
        return glob.iglob(pathpattern)
    elif tokens is not None:
        return chain.from_iterables(glob.iglob(token) for token in tokens)
    else:
        return glob.iglob('**/*')

@wrap
def words(n=0, word='\S+', outsep=None, names=None, inject=None, flags=0, tokens=None):
    """
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
    :param word: a pattern that will be used to select words using :py:func:`re.findall`
    :param outsep: a string separator to join together the words that are found into a new string (or None to output a list of words)
    :param names: (Optional) a name or list of names of the n extracted words, used to construct a dict to be passed down the pipeline
    :param inject: For use with ``names`` - extra key/value pairs to include in the output dict
    :param flags: flags to pass to the re engine to compile the pattern
    :param tokens: list of tokens to iterate through in the function (usually supplied by the previous function in the pipeline)
    :raise ValueError: if there are less than n (or max(n)) words in the string
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
    for line in tokens:
        result=line.split(sep)
        yield _ntodict(result, n, names, inject) if not outsep else outsep.join(_ntodict(result, n, names, inject))

@wrap
def tokenize(pattern, groups=None, names=None, match=True, flags=0, inject={}, tokens=None):
    """
    Docs for tokenize

    :param pattern:
    :param groups:
    :param names:
    :param match:
    :param flags:
    :param inject:
    :param tokens:
    :raise TypeError:

    """
    if isinstance(pattern, string_types):
        matcher=re.compile(pattern, flags=flags)
        for line in tokens:
            result = matcher.match(line) if match else matcher.search(line)
            if not result:
                raise ValueError('Pattern %s does not match %s' % (pattern, line))
            d=_groupstodict(result, groups, names, inject)
            yield d
    else:
        raise TypeError('tokenize only supports matching by strings (not strings of strings) so far')

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

    :param converters: ``dict`` of functions or ``list`` of functions or function that converts a field from one form to another
    :param defaults: defaults to use if the converter function returns
    `ValueError` (should be the same type as converters)
    :param tokens: a series of ``dict`` or ``list`` of things to be converted
    or a series of things
    :raise: ValueError if the conversion fails and no default is supplied
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
def sfilter(filterfunction=None, tokens=None):
    """

    Take a user-defined function and passes through the tokens for which the function returns something that is True
    in a conditional context. If no function is supplied, passes through the True items. (Equivalent of :py:func:``filter``)
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
        else:
            raise TypeError('Format expects a sequence or a mapping - got a %s' % type(token))

if __name__=='__main__':
    import doctest
    doctest.testmod()
    output= read('streamutils/__init__.py') | matches('def') | matches('streamutils.py') | search('(.prin.)', n=0)
    output= head(10, 'streamutils/__init__.py')
    output= printList() | matches('a')
    output=tail(10, 'streamutils/__init__.py')
    for f in output:
        print('Result: %s ' % f.strip())
    print('Done')
