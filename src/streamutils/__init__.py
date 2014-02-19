#!/usr/bin/env python2.7
# coding: utf-8
# vim: set tabstop=4 shiftwidth=4 expandtab:
# Implementation of bash style function piping
# Some implementation details from http://www.dabeaz.com/generators/

from __future__ import unicode_literals, print_function, division

from six import StringIO, string_types, integer_types

import re, time, codecs, subprocess, os, glob, locale, shlex
from collections import Iterable, Callable, Iterator, deque, OrderedDict, Mapping, Sequence, Counter
from itertools import chain

__author__='maxgrenderjones'

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
        #print('Create a composable function by wrapping %s which takes tokens as "%s"' % (func.__name__, tokenskw))
        self.func=func
        self.tokenskw=tokenskw
    def __call__(self, *args, **kwargs):
        #print 'Calling via ConnectingGenerator'
        return ConnectingGenerator(self.func, self.tokenskw, args, kwargs)
    def __getattr__(self, name):
        #Kludge (ish) to allow sh's attribute access to work
        f=getattr(self.func, name)
        if (callable(f)):
            return wrap(f)

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

class Terminator(Callable):
    def __init__(self, func, tokenskw):
        #print('Create a terminating function by wrapping %s which takes tokens as "%s"' % (func.__name__, tokenskw))
        self.func=func
        self.tokenskw=tokenskw

    def __call__(self, *args, **kwargs):
        self.args=args
        self.kwargs=kwargs
        return self #We don't do anything yet, as tokens won't be set yet - func is called by the
                    #OR inside the ConnectingGenerator, after setting tokens


'''
    Tries to guess what encoding to use to open a file based on first few lines. Supports xml and python
    declaration as per http://www.python.org/dev/peps/pep-0263/
'''
def eopen(fname, encoding=None):
    if not encoding:
        encoding=head(tokens=open(fname), n=2) | search(r'coding[:=]\s*"?([-\w.]+)"?', 1) | first()
    if encoding:
        #print('Opening file %s with encoding %s' % (fname, encoding))
        return codecs.open(fname, encoding=encoding)
    else:
        return open(fname)


def wrap(func, tokenskw='tokens'):
    return ComposableFunction(func, tokenskw)

def wrapTerminator(func, tokenskw='tokens'):
    return Terminator(func, tokenskw)

def wrapInIterable(item):
    if isinstance(item, integer_types) or isinstance(item, string_types):
        return [item]
    elif isinstance(item, Iterable):
        return item
    elif hasattr(item, '__iter__'):
        return item
    else:
        return [item]

@wrap
def printList():
    return ['a', 'b', 'c']

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
def all(tokens=None):
    return list(tokens)

@wrapTerminator
def nth(n, default=None, tokens=None):
    cur=1
    for line in tokens:
        if cur==n:
            return line
        cur+=1
    return default

@wrapTerminator
def sort(cmp=None, key=None, reverse=False, tokens=None):
    return sorted(tokens, cmp, key, reverse)

@wrapTerminator
def count(tokens=None):
    return sum(1 for line in tokens)

@wrapTerminator
def bag(tokens=None):
    return Counter(tokens)

@wrapTerminator
def action(func, tokens=None):
    for line in tokens:
        func(line)

@wrapTerminator
def write(fname=None, encoding=None, tokens=None):
    if not fname:
        for line in tokens:
            print(line)
    elif isinstance(fname, string_types):
        with codecs.open(fname, encoding=encoding, mode='wb') if encoding else open(fname, mode='wU') as f:
            f.writelines(tokens)
    else:
        for line in tokens:
            fname.write(line)

@wrap
def unique(tokens=None):
    s=set()
    for line in tokens:
        if line not in s:
            s.add(line)
            return s


@wrap
def head(n=10, fname=None, encoding=None, tokens=None):
    if fname:
        tokens=eopen(fname)
    try:
        if tokens is not None:
            for i, line in zip(range(0,10), tokens):
                yield line
        else:
            ValueError('Either fname or tokens must be set')
    finally:
        if fname:
            tokens.close()

@wrap
def tail(n=10, fname=None, encoding=None, tokens=None):
    if fname:
        tokens=eopen(fname)
    try:
        if tokens is not None:
            return deque(tokens, n)
        else:
            ValueError('Either fname or tokens must be set')
    finally:
        if fname:
            tokens.close()

@wrap
def follow(fname, encoding=None):
    f = eopen(fname, encoding, )
    f.seek(0, os.SEEK_END)
    while True:
        line = f.readline()
        if not line:
            time.sleep(1)
            continue
        yield line

@wrap
def stream(fname, encoding=None):
    files=wrapInIterable(fname)
    for name in files:
        with eopen(name, encoding) as f:
            for line in f:
                #print 'Cat: %s' % line.strip()
                yield line

@wrap
def search(pattern, group=0, to=None, match=False, fname=None, encoding=None, flags=0, tokens=None):
    matcher = re.compile(pattern) if not flags else re.compile(pattern, flags=flags)
    if fname is not None:
        tokens=stream(fname, encoding)
    for line in tokens:
        if not to:
            result = matcher.match(line) if match else matcher.search(line)
            if not result:
                continue
            yield result.group(group)
        else:
            yield matcher.sub(pattern, to, line)

@wrap
def replace(text, replacement, tokens=None):
    for line in tokens:
        yield line.replace(text, replacement)

@wrap
def matches(pattern, flags=0, match=False, v=False, tokens=None):
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
def nomatch(pattern, flags=0, match=False, tokens=None):
    for token in matches(pattern=pattern, flags=flags, match=match, v=True, tokens=tokens):
        yield token
@wrap
def fnmatches(pathpattern, matchcase=False, tokens=None):
    import fnmatch
    for line in tokens:
        line.replace(os.sep, '/')
        if matchcase and fnmatch.fnmatchcase(line, pathpattern):
            yield line
        elif not matchcase and fnmatch.fnmatch(line, pathpattern):
            yield line
@wrap
def find(pathpattern=None, tokens=None):
    if pathpattern:
        return glob.iglob(pathpattern)
    elif tokens is not None:
        return chain.from_iterables(glob.iglob(token) for token in tokens)
    else:
        raise ValueError('Nothing to find')

@wrap
def words(n, word='\S+', outsep=' ', flags=0, tokens=None):
    matcher=re.compile(word) if not flags else re.compile(word, flags=flags)
    n=wrapInIterable(n)
    for line in tokens:
        result=matcher.findall(line)
        if len(result)<max(n):
            raise ValueError('%s does not have %d words using word pattern %s' % (line, max(n), word))
        if outsep is not None:
            yield outsep.join([result[i-1] for i in n])
        else:
            yield [result[i-1] for i in n]

@wrap
def split(n, sep=None, outsep=' ', tokens=None):
    n=wrapInIterable(n)
    for line in tokens:
        result=line.split(sep)
        if len(result)<max(n):
           raise ValueError('%s does not have %d words using separator %s' % (line, max(n), sep))
        yield outsep.join(result[i-1] for i in n)

@wrap
def tokenize(pattern, groups=None, names=None, match=True, flags=0, inject={}, tokens=None):
    if isinstance(pattern, string_types):
        matcher=re.compile(pattern, flags=flags)
        for line in tokens:
            result = matcher.match(line) if match else matcher.search(line)
            if not result:
                raise ValueError('Pattern %s does not match %s' % (pattern, line))
            if groups is not None:
                d=OrderedDict(zip(groups, result.groups()))
                d.update(inject)
                yield d
            elif names is not None:
                d=OrderedDict([(group, result.group(group)) for group in names])
                d.update(inject)
                yield d
            else:
                yield result.groups()
    else:
        raise TypeError('tokenize only supports matching by strings (not strings of strings) so far')

@wrap
def convert(converters, defaults={}, tokens=None):
    for line in tokens:
        for field in converters:
            if field in line:
                try:
                    line[field]=converters[field](line[field])
                except ValueError:
                    if field in defaults:
                        line[field]=defaults[field]
                    else:
                        raise
        yield line

@wrap
def transform(transformation, tokens=None):
    for line in tokens:
        return transformation(line)


@wrap
def reformat(pattern, tokens=None):
    for token in tokens:
        if isinstance(token, Sequence):
            yield pattern.format(*token)
        elif isinstance(token, Mapping):
            yield pattern.format(*token.values(), **token)
        else:
            raise TypeError('Format expects a sequence or a mapping - got a %s' % type(token))

if __name__=='__main__':
    output= stream('__init__.py') | matches('def') | matches('streamutils.py') | search('(.prin.)', n=0)
    output= head(10, '__init__.py')
    output= printList() | matches('a')
    output=tail(10, '__init__.py')
    for f in output:
        print('Result: %s ' % f.strip())
    print('Done')
