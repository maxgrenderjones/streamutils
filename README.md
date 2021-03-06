streamutils - pipelines for python
==================================
Bringing one-liners to python since 2014

[![Build Status](https://travis-ci.org/maxgrenderjones/streamutils.png "Build status at Travis-CI")](https://travis-ci.org/maxgrenderjones/streamutils/) [![Coverage Status](https://coveralls.io/repos/maxgrenderjones/streamutils/badge.png?branch=master)](https://coveralls.io/r/maxgrenderjones/streamutils?branch=master)

Motivation
----------

Have you ever been jealous of friends who know more commandline magic than you? Perhaps you're a python user who feels guilty that you never learnt [sed], [awk] or [perl], and wonder quite how many keystrokes you could be saving yourself? (On the plus side, you haven't worn the keycaps off your punctuation keys yet). Or maybe you're stuck using (or supporting) windows?

Or perhaps you are one of those friends, and your heart sinks at the thought of all the for loops you'd need to replicate a simple `grep "$username" /etc/passwd | cut -f 1,3 -d : --output-delimiter=" "` in python? Well, hopefully streamutils is for you.

Put simply, streamutils is a pythonic implementation of the pipelines offered by unix shells and the coreutils toolset. Streamutils is not (at least not primarily) a python wrapper around tools that you call from the commandline or a wrapper around `subprocess`  (for that, you want [sh] or its previous incarnation [pbs]). However, it can interface with external programmes through its `run` command.

Enough already! What does it do? Perhaps it's best explained with an example. Suppose you want to reimplement our bash pipeline outlined above:

```python
>>> from __future__ import print_function
>>> from streamutils import *
>>> name_and_userid = read('examples/passwd') | matches('johndoe') | split([1,3], ':', ' ') | first()
>>> print(name_and_userid)
johndoe 1000
>>> gzread('examples/passwd.gz') | matches('johndoe') | split([1,3], ':', ' ') | write() #Can read from gzipped (and bzipped) files
johndoe 1000
>>> gzread('examples/passwd.gz', encoding='utf8') | matches('johndoe') | split([1,3], ':', ' ') | write() #You really ought to specify the unicode encoding
johndoe 1000
>>> read('examples/passwd.bz2', encoding='utf8') | matches('johndoe') | split([1,3], ':', ' ') | write() #streamutils will attempt to transparently decompress compressed files (.gz, .bz2, .xz)
johndoe 1000
>>> read('examples/passwd.xz', encoding='utf8') | matches('johndoe') | split([1,3], ':', ' ') | write() 
johndoe 1000
```

streamutils also mimics the `>` and `>>` operators of bash-like shells, so to write to files you can write something like:

```python
>>> import tempfile, shutil, os
>>> try:
...     #Some setup follows to allow this docstring to be included in automated tests
...     tempdir=tempfile.mkdtemp() # Create a temporary directory to play with
...     cwd=os.getcwd()            # Save the current directory so we can change back to it afterwards
...     os.chdir(tempdir)          # Change to our temporary directory
...     passwd=os.path.join(cwd, 'examples', 'passwd.gz')
...     #Right - setup's done
...     with open('test.txt', mode='w') as tmp:                                    # mode determines append / truncate behaviour
...         gzread(passwd) | matches('johndoe') | split([1,3], ':', ' ') > tmp     # can write to open things
...     # >> appends, but because python evaluates rshifts (>>) before bitwise or (|), the preceding stream must be in brackets
...     (gzread(passwd) | matches('johndoe') | split([1,3], ':', ' ')) >> 'test.txt'
...     line = read('test.txt') | first()
...     assert line.strip()=='johndoe 1000'
...     length = read('test.txt') | count()
...     assert length==2
...     gzread(passwd) | matches('johndoe') | split([1,3], ':', ' ') > 'test.txt'  # (> writes to a new file)
...     length = read('test.txt') | count()
...     assert length==1
... finally:
...     os.chdir(cwd)           # Go back to the original directory
...     shutil.rmtree(tempdir)  # Delete the temporary one
...
```

Or perhaps you need to start off with output from a real command:
```python
>>> from streamutils import *
>>> import platform
>>> cat = 'python -c "import sys; print(open(sys.argv[1]).read())"' if platform.system()=='Windows' else 'cat' 
>>> run('%s setup.py' % cat) | search("keywords='(.*)'", group=1) | write()
UNIX pipelines for python
```

You don't have to take your input from a file or some other `streamutils` source, as it's easy to pass in an `Iterable` that you've created elsewhere to have some functional programming fun:
```python
>>> from streamutils import *
>>> 1 | smap(float) | aslist() # Non-iterables are auto-wrapped
[1.0]
>>> ['d', 'c', 'b', 'a'] | smap(lambda x: (x.upper(), x)) | ssorted(key=lambda x: x[0]) | smap(lambda x: x[1]) | aslist() # Streamutils' Schwartzian transform (sorting against an expensive-to-compute key)
['a', 'b', 'c', 'd']
>>> range(0,1000) | sfilterfalse(lambda x: (x%5) * (x%3)) | ssum() # Euler1: sum of first 1000 numbers divisible by 3 or 5
233168
>>> import itertools
>>> def fib():
...     fibs={0:1, 1:1}
...     def fibn(n):
...         return fibs[n] if n in fibs else fibs.setdefault(n, fibn(n-1)+fibn(n-2))
...     for f in itertools.count(0) | smap(fibn):
...         yield f
...
>>> fib() | takewhile(lambda x: x<4000000) | sfilterfalse(lambda x: x%2) | ssum() # Euler 2: sum of even fibonacci numbers under four million
4613732
>>> (range(0, 101) | ssum())**2 - (range(0,101) | smap(lambda x: x*x) | ssum()) # Euler 6: difference between the sum of the squares of the first one hundred natural numbers and the square of the sum.
25164150
>>> top = 110000
>>> primes=range(2,top)
>>> for p in range(2,int(top**0.5)): # Euler 7: Sieve of Eratosthenes
...     primes|=sfilter(lambda x: (x==p) or (x%p), end=True)
...
>>> primes|nth(10001)
104743
```

Features
--------

-   Lazy evaluation and therefore memory efficient - nothing happens until you start reading from the output of your pipeline, when each of the functions runs for just long enough to yield the next token in the stream (so you can use a pipeline on a big file without needing to have enough space to store the whole thing in memory)
-   Extensible - to use your own functions in a pipeline, just decorate them, or use the built in functions that do the groundwork for the most obvious things you might want to do (i.e. custom filtering with `sfilter`, whole-line transformations with `smap` or partial transformations with `convert`)
-   Unicode-aware: all functions that read from files or file-like things take an `encoding` parameter
-   Not why I wrote the library at all but as shown above many of `streamutils` functions are 'pure' in the functional sense, so if you squint your eyes, you might be able to think of this as a way into functional programming, with a much nicer syntax (imho, as function composition reads left to right not right to left, which makes it more readable if less pythonic) than say [toolz](https://github.com/pytoolz/toolz)

Non-features
------------

An unspoken element of the zen of python (`import this`) is 'Fast to develop' is better than 'Fast to run', and if there's a downside to `streamutils` that's it. The actual bash versions of `grep` etc are no doubt much faster than `search`/`match` from `streamutils`. But then you can't call python functions from them, or call them from python code on your windows machine. As they say, 'you pays your money and you take your choice'. Since `streamutils` uses so many unsupported features (generators, default args, context managers), using `numba` to get speed-ups for free would sadly appear to not be an option for now (at least not without the help of a `numba`-expert) and though `cython` (as per `cytoolz`) would certainly work it would make `streamutils` much harder to install and would require a lot more effort.

Functions
---------
A quick bit of terminology:

- **pipeline**: A series of streamutil functions joined together with pipes (i.e. `|`)
- **tokens**: things being passed through the pipeline
- **stream**: the underlying data which is being broken into the tokens that are passed through the pipeline

Implemented so far (equivalent `coreutils` function in brackets if the name is different). Note that the following descriptions say 'lines', but there's nothing stopping the functions operating on a stream of tokens that aren't newline terminated strings:

### Connectors
These are functions designed to start a stream or process a stream (the underlying functions are wrapped via `@connector` and either return an `Iterator` or `yield` a series of values). Result is something that can be iterated over

Functions that act on one token at a time:

-   `read`, `gzread`, `bzread`, `head`, `tail`, `follow` to: read a file (`cat`); read a file from a gzip file (`zcat`); read a file from a bzip file (`bzcat`); extract the first few tokens of a stream; the last few tokens of a stream; to read new lines of a file as they are appended to it (waits forever like `tail -f`)
-   `csvread` to read a csv file
-   `matches`, `nomatch`, `search`, `replace` to: match tokens (`grep`), find lines that don't match (`grep -v`), to look for patterns in a string (via `re.search` or `re.match`) and return the groups of lines that match (possibly with substitution); replace elements of a string (i.e. implemented via `str.replace` rather than a regexp)
-   `find`, `fnmatches` to: look for filenames matching a pattern; screen names to see if they match
-   `split`, `join`, `words` to: split a line (with `str.split`) and return a subset of the line (``cut``); join a line back together (with `str.join`), find all non-overlapping matches that correspond to a 'word' pattern and return a subset of them
-   `sformat` to: take a `dict` or `list` of strings (e.g. the output of `words`) and format it using the `str.format` syntax (`format` is a builtin, so it would be bad manners not to rename this function).
-   `sfilter`, `sfilterfalse` to: take a user-defined function and return the items where it returns True; or False. If no function is given, it returns the items that are `True` (or `False`) in a conditional context
-   `unique` to: only return lines that haven't been seen already (`uniq`)
-   `update`: that updates a stream of `dicts` with another `dict`, or takes a `dict` of `key`, `func` mappings and calls the `func` against each `dict` in the stream to get a value to assign to each `key`
-   `smap`, `convert` to: take user-defined function and use it to `map` each line; take a `list` or `dict` (e.g. the output of `search`) and call a user defined function on each element (e.g. to call `int` on fields that should be integers)
-   `takewhile`, `dropwhile` to: yield elements while a predicate is `True`; drop elements until a predicate is `False`
-   `unwrap`, `traverse`: to remove one level of nested lists; to do a depth first search through supplied iterables

Stream modifiers:

-   `separate`, `combine`: to split the tokens in the stream so that the remainder of the stream receives sub-tokens; to combine subtokens back into tokens


### Terminators
These are functions that end a stream (the underlying functions are wrapped in `@terminator` and `return` their values). Result may be a single value or a list (or something else - point is, not a generator). As soon as you apply a `Terminator` to a stream it computes the result.

-   `first`, `last`, `nth` to: return the first item of the stream; the last item of the stream; the nth item of the stream
-   `count`, `bag`, `ssorted`, `ssum`: to return the number of tokens in the stream (`wc`); a `collections.Counter` (i.e. `dict` subclass) with unique tokens as keys and a count of their occurences as values; a sorted list of the tokens; add the tokens. (Note that `ssorted` is a terminator as it needs to exhaust the stream before it can start working)
-   `write`: to write the output to a named file, or print it if no filename is supplied, or to a writeable thing (e.g an already open file) otherwise.
-   `csvwrite`: to write to a csv file
-   `sumby`, `meanby`, `firstby`, `lastby`, `countby`: to aggregate by a key or keys, and then sum / take the mean / take the first / take the last / count
-   `sreduce`: to do a pythonic `reduce` on the stream
-   `action`: for every token, call a user-defined function
-   `smax`, `smin` to: return the maximum or minimum element in the stream
-   `nsmallest`, `nlargest` to: find the n smallest or n largest elements in the stream

Note that if you have a `Iterable` object (or one that behaves like an iterable), you can pass it into the first function of the pipeline as its `tokens` argument.

### Other
To facilitate stream creation, the `merge` function can be used to join two streams together `SQL`-style (`left`/`inner`/`right`)

API Philosophy & Conventions
----------------------------
There are a number of tenets to the API philosophy, which is intended to maximise backward and forward compatibility and minimise surprises - while the API is in flux, if functions don't fit the tenets (or tenets turn out to be flawed - feedback welcome!) then the API or tenets will be changed. If you remember these, you should be able to guess (or at least remember) what a function will be called, and how to call it. These tenets are:

-   Functions should have sensible names (none of this `cat` / `wc` nonsense - apologies to you who are so trained as to think that `cat` *is* the sensible name...)
-   These names should be as close as possible to the name of the related function from the python library. It's ok if the function names clash with their vanilla counterparts from a module (e.g. there's a function called `search` in `re` too), but not if they clash with builtin functions - in that case they get an `s` prepended (hence `sfilter`, `sfilterfalse`, `sformat`). (For discussion: is this the right idea? Would it be easier if all functions had s prefixes?)
-   If you need to avoid clashes, `import streamutils as su` (which has the double benefit of being nice and terse to keep your pipelines short, and will help make you [all powerful](http://xkcd.com/149/))
-   Positional arguments that are central to what a function does come first (e.g. `n`, the number of lines to return, is the first argument of `head`) and their order should be stable over time. For brevity, they should be given sensible defaults. If additional keyword arguments are added, they will be added after existing ones. After the positional arguments comes `fname`, which allows you to avoid using `read`. To be safe, apart from for `read`, `head`, `tail` and `follow`, `fname` should therefore be called as a keyword argument as it marks the first argument whose position is not guaranteed to be stable.
-   `tokens` is the last keyword argument of each function
-   If it's sensible for the argument to a function to be e.g. a string or a list of strings then both will be supported (so if you pass a list of filenames to `read` (via `fname`), it will `read` each one in turn).
-   `for line in open(file):` iterates through a set of `\n`-terminated strings, irrespective of `os.linesep`, so other functions yielding lines should follow a similar convention (for example `run` replaces `\r\n` in its output with `\n`)
-   This being the 21st century, streamutils opens files in unicode mode (it uses `io.open` in text mode). The benefits of slow-processing outweigh the costs. I am not opposed to adding `readbytes` if there is demand (which would return `str` or `bytes` depending on your python version)
-   `head(5)` returns the first 5 items, similarly `tail(5)` the last 5 items. `search(pattern, 2)`, `word(3)` and `nth(4)` return the second group, third 'word' and fourth item (not the third, fourth and fifth items). This therefore allows `word(0)` to return all words. Using zero-based indexing in this case feels wrong to me - is that too confusing/suprising? (Note that this matches how the coreutils behave, and besides, python is inconsistent here - `group(1)` is the first not second group, as `group(0)` is reserved for the whole pattern).

I would be open to creating a `coreutils` (or similarly named) subpackage, which aims to roughly replicate the names, syntax and flags of the `coreutils` toolset (i.e. `grep`, `cut`, `wc` and friends), but only if they are implemented as thin wrappers around streamutils functions. After all, the functionality they provide is tried and tested, even if their names were designed primarily to be short to type (rather than logical, memorable or discoverable).

Installation and Dependencies
-----------------------------

`streamutils` supports python >=2.6 (on 2.6 it needs the `OrderedDict` and `Counter` backports, on <3.3 it can use the `lzma` backport), and python >=3 by using the [six] library (note that >=1.4.1 is required). Ideally it would support [pypy] too, but support for `partial` functions in the released versions of [pypy] is [broken](https://bitbucket.org/pypy/pypy/issue/2043/) at the time of writing.

For now, the easiest way to install it is to pull the latest version direct from github by running:

    pip install git+https://github.com/maxgrenderjones/streamutils.git#egg=streamutils

Once it's been submitted to [pypi], if you've already got the dependencies installed, you'll be able to install streamutils from [pypi] by running:

    pip install streamutils

If you want pip to install the mandatory dependencies for you, then run:

    pip install streamutils[deps]

Alternatively, you can install from the source by running:

    python setup.py install

If you don't have [pip], which is now the official way to install python packages (assuming your package manager isn't doing it for you) then use your package manager to install it, or if you don't have one (hello Windows users), download and run https://raw.github.com/pypa/pip/master/contrib/get-pip.py

Status
------
`streamutils` is currently beta status. By which I mean:
-   I think it works fine, but there may be edge cases I haven't yet thought of (found one? submit a bug report, or better, a pull request)
-   The API is unstable, i.e. the names of functions are still in flux, the order of the positional arguments may change, and the order of keyword arguments is almost guaranteed to change

So why release?
-   Because as soon as I managed to get `streamutils` working, I couldn't stop thinking of all the places I'd want to use it
-   Because I value feedback on the API - if you think the names of functions or their arguments would be more easily understood if they were changed then open an issue and let's have the debate
-   Because it's a great demonstration of the crazy stuff you can do in python by overloading operators
-   Why not?

How does it work?
-----------------
You don't need to know this to use the library, but you may be curious nonetheless - if you want, you can skip this section. (Warning: this may make your head hurt - it did mine). In fact, the core of the library is only ~100 lines, but it took me a *lot* of time to find those magic 100 lines. The answer is a mixture of generators, partials and overloaded operators. (So wrong it's right? You decide...) Let's explain it with the example of a naive pipeline designed to find module-level function names within `ez_setup.py`:
```python
>>> from streamutils import *
>>> s = read('ez_setup.py') | search(r'^def (\w+)[(]', 1) #Nothing really happens yet
>>> first_function = s | first()                          #Only now is read actually called
>>> print(first_function)
_python_cmd
```
So what happened?

In order:

-   Functions used in pipelines are expected to (optionally) take as input an `Iterable` thing (as a keyword argument called `tokens` - in future, it should be possible to use any name), and use it to return an `Iterable` thing, or `yield` a series of values
-   Before using a function in a pipeline, it must be wrapped (via either `@connector` or `@terminator` decorators). This wraps the function in a special `Callable` which defers execution, so, taking `read` (equivalent of unix `cat`) as an example, if you write `s=read('ez_setup.py')` then you haven't actually called the underlying `read` function but the `__call__` method of the `Connector` it's wrapped in. This `__call__` method wraps the original `read` function in a [partial], which you can think of as a preprimed function object - i.e. when you call it, it calls the underlying function with the arguments you supplied when creating the partial.
The `__call__` method itself therefore returns a `Connector` (which implements the basic `generator` functions) which waits for something to iterate over `s` or to compose (i.e. `|`) `s` with another `Connector`. When something starts iterating over a `Connector`, it passes through the values `yield`-ed by the  underlying function (i.e. `read`). So far, so unremarkable.
-   But, and here's where the magic happens, when you `|` a call to `read` with another wrapped function e.g. `search`, then the output of the `read` function is called and to the `tokens` keyword argument of `search`. But assuming `read` is a `generator` function nothing has really happened, the functions have simply been wired together

Two options for what you do next:

-   You iterate over `s`, in which case the functions are finally called and the results are passed down the chain. (Your `for` loop would iterate over the function names in `ez_setup.py`)
-   You compose `s` with a function (in this case `first`)  that has been decorated with `@terminator` to give a `Terminator`. A `Terminator` completes the pipeline and will `return` a value, not `yield` values like a `generator`. (Strictly speaking, when you call a `Terminator` nothing happens. It's only when the `__or__` function (i.e. the `|` bitwise OR operator) is called betwen a `Connector` and a `Terminator` that the function wrapped in the `Terminator` is called and the chain of generators yield their values.)

Contribute
----------

- Issue Tracker: http://github.com/maxgrenderjones/streamutils/issues
- Source Code: http://github.com/maxgrenderjones/streamutils
- API documentation: http://streamutils.readthedocs.org/
- Continuous integration: [![Build Status](https://travis-ci.org/maxgrenderjones/streamutils.png "Build status at Travis-CI")](https://travis-ci.org/maxgrenderjones/streamutils/)
- Test coverage: [![Coverage Status](http://coveralls.io/repos/maxgrenderjones/streamutils/badge.png?branch=master "Coverage status at Coveralls")](https://coveralls.io/r/maxgrenderjones/streamutils)

Alternatives and Prior art
--------------------------
Various other projects either abuse the `|` operator or try to make it easy to compose functions with iterators, none of which seem as natural to me (but some have syntax much closer to functional programming), so ymmv:

 - [Pipe](https://github.com/JulienPalard/Pipe) - probably the closest to `streamutils`, but less focussed on file/text processing, and has fewer batteries included
 - [toolz](https://github.com/pytoolz/toolz)
 - [Rich Iterator Wrapper](https://code.activestate.com/recipes/498272-rich-iterator-wrapper/?in=user-2591466)
 - [fn.py](https://github.com/kachayev/fn.py)

Acknowledgements and References
-------------------------------
A shout-out goes to David Beazley, who has written the most comprehensible (and comprehensive) documentation that I've seen on [how to use generators](http://www.dabeaz.com/generators/)

Apache log file example provided by [Nasa](http://ita.ee.lbl.gov/html/contrib/NASA-HTTP.html)

[perl]: http://perl.org
[sed]: http://www.gnu.org/software/sed/
[awk]: http://www.gnu.org/s/gawk/manual/gawk.html
[sh]: https://pypi.python.org/pypi/sh
[pbs]: https://pypi.python.org/pypi/pbs
[pypi]: https://pypi.python.org/
[six]: https://pythonhosted.org/six/
[pip]: http://pip.readthedocs.org/en/latest/installing.html
[partial]: https://docs.python.org/2/library/functools.html#functools.partial
[pypy]: http://pypy.org/

License
-------

The project is licensed under the [Eclipse Public License - v 1.0](http://choosealicense.com/licenses/eclipse/)
