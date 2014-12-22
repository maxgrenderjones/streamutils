streamutils - pipelines for python
==================================

Bringing one-liners to python since 2014

|Build Status| |Coverage Status|

Motivation
----------

Have you ever been jealous of friends who know more commandline magic
than you? Perhaps you're a python user who feels guilty that you never
learnt `sed <http://www.gnu.org/software/sed/>`__,
`awk <http://www.gnu.org/s/gawk/manual/gawk.html>`__ or
`perl <http://perl.org>`__, and wonder quite how many keystrokes you
could be saving yourself? (On the plus side, you haven't worn the
keycaps off your punctuation keys yet). Or maybe you're stuck using (or
supporting) windows?

Or perhaps you are one of those friends, and your heart sinks at the
thought of all the for loops you'd need to replicate a simple
``grep "$username" /etc/passwd | cut -f 1,3 -d : --output-delimiter=" "``
in python? Well, hopefully streamutils is for you.

Put simply, streamutils is a pythonic implementation of the pipelines
offered by unix shells and the coreutils toolset. Streamutils is not (at
least not primarily) a python wrapper around tools that you call from
the commandline or a wrapper around ``subprocess``. For that, you want
`sh <https://pypi.python.org/pypi/sh>`__ or its previous incarnation
`pbs <https://pypi.python.org/pypi/pbs>`__.

Enough already! What does it do? Perhaps it's best explained with an
example. Suppose you want to reimplement our bash pipeline outlined
above:

.. code:: python

    >>> from __future__ import print_function
    >>> from streamutils import *
    >>> name_and_userid = read('examples/passwd') | matches('johndoe') | split([1,3], ':', ' ') | first()
    >>> print(name_and_userid)
    johndoe 1000
    >>> gzread('examples/passwd.gz') | matches('johndoe') | split([1,3], ':', ' ') | write() #Can read from gzipped (and bzipped) files
    johndoe 1000

streamutils also mimics the ``>`` and ``>>`` operators of bash-like
shells, so to write to files you can write something like:

.. code:: python

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

Or perhaps you need to start off with output from a real command
(streamutils wraps
`sh <https://pypi.python.org/pypi/sh>`__/`pbs <https://pypi.python.org/pypi/pbs>`__):

.. code:: python

    >>> from streamutils import *
    >>> edited=sh.git.status() | matches('modified:') | words(2)    # doctest: +SKIP
    >>> for edit in edited:                                         # doctest: +SKIP
    ...    print(edit)
    ...
    readme.md
    src/streamutils/__init__.py

(Or alternatively, if you don't want to install
`sh <https://pypi.python.org/pypi/sh>`__/`pbs <https://pypi.python.org/pypi/pbs>`__)

.. code:: python

    >>> from streamutils import *
    >>> edited=run(['git', 'status']) | matches('modified:') | words(2) # doctest: +SKIP
    >>> for edit in edited:                                             # doctest: +SKIP
    ...    print(edit)
    ...
    README.md
    src/streamutils/__init__.py

Features
--------

-  Lazy evaluation and therefore memory efficient - nothing happens
   until you start reading from the output of your pipeline, when each
   of the functions runs for just long enough to yield the next token in
   the stream (so you can use a pipeline on a big file without needing
   to have enough space to store the whole thing in memory)
-  Extensible - to use your own functions in a pipeline, just decorate
   them, or use the built in functions that do the groundwork for the
   most obvious things you might want to do (i.e. custom filtering with
   ``filter``, whole-line transformations with ``transform`` or partial
   transformations with ``convert``)
-  Unicode-aware: all functions that read from files or file-like things
   take an ``encoding`` parameter

Functions
---------

A quick bit of terminology: - **pipeline**: A series of streamutil
functions joined together with pipes (i.e. ``|``) - **tokens**: things
being passed through the pipeline - **stream**: the underlying data
which is being broken into the tokens that are passed through the
pipeline

Implemented so far (equivalent ``coreutils`` function in brackets if the
name is different). Note that the following descriptions say 'lines',
but there's nothing stopping the functions operating on a stream of
tokens that aren't newline terminated strings:

Composable Functions
~~~~~~~~~~~~~~~~~~~~

These are functions designed to start a stream or process a stream.
Result is something that can be iterated over

Implemented: - ``read``, ``gzread``, ``bzread``, ``head``, ``tail``,
``follow`` to: read a file (``cat``); read a file from a gzip file
(``zcat``); read a file from a bzip file (``bzcat``); extract the first
few tokens of a stream; the last few tokens of a stream; to read new
lines of a file as they are appended to it (waits forever like
``tail -f``) - ``matches``, ``nomatch``, ``search``, ``replace`` to:
match tokens (``grep``), find lines that don't match (``grep -v``), to
look for patterns in a string (via ``re.search`` or ``re.match``) and
return the groups of lines that match (possibly with substitution);
replace elements of a string (i.e. implemented via ``str.replace``
rather than a regexp) - ``find``, ``fnmatches`` to: look for filenames
matching a pattern; screen names to see if they match - ``split``,
``join``, ``words`` to: split a line (with ``str.split``) and return a
subset of the line (``cut``); join a line back together (with
``str.join``), find all non-overlapping matches that correspond to a
'word' pattern and return a subset of them - ``sformat`` to: take a
``dict`` or ``list`` of strings (e.g. the output of ``words``) and
format it using the ``str.format`` syntax (``format`` is a builtin, so
it would be bad manners not to rename this function). - ``sfilter``,
``sfilterfalse`` to: take a user-defined function and return the items
where it returns True; or False. If no function is given, it returns the
items that are ``True`` (or ``False``) in a conditional context -
``unique`` to: only return lines that haven't been seen already
(``uniq``) - ``transform``, ``convert`` to: take user-defined function
and use it to transform each line; take a ``list`` or ``dict`` (e.g. the
output of ``search``) and call a user defined function on each element
(e.g. to call ``int`` on fields that should be integers)

Not yet implemented: - ``separate``, ``combine``: to split the tokens in
the stream so that the remainder of the stream receives sub-tokens; to
combine subtokens back into tokens

Terminators
~~~~~~~~~~~

These are functions that end a stream. Result may be a single value or a
list (or something else - point is, not a generator).

Implemented: - ``first``, ``last``, ``nth`` to: return the first item of
the stream; the last item of the stream; the nth item of the stream -
``count``, ``bag``, ``sort``, ``ssum``: to return the number of tokens
in the stream (``wc``); a ``collections.Counter`` (i.e. ``dict``
subclass) with unique tokens as keys and a count of their occurences as
values; a sorted list of the tokens; add the tokens. (Note that ``sort``
is a terminator as a reminder that that it needs to exhaust the stream
before it can start working) - ``write``: to write the output to a named
file, or print it if no filename is supplied, or to a writeable thing
(e.g an already open file) otherwise. - ``sreduce``: to do a pythonic
``reduce`` on the stream - ``action``: for every token, call a
user-defined function - ``smax``, ``smin`` to: return the maximum or
minimum element in the stream

Note that if you have a ``Iterable`` object (or one that behaves like an
iterable), you can pass it into the first function of the pipeline as
its ``tokens`` argument.

API Philosophy & Conventions
----------------------------

There are a number of tenets to the API philosophy, which is intended to
maximise backward and forward compatibility and minimise surprises -
while the API is in flux, if functions don't fit the tenets (or tenets
turn out to be flawed - feedback welcome!) then the API or tenets will
be changed. If you remember these, you should be able to guess (or at
least remember) what a function will be called, and how to call it.
These tenets are:

-  Functions should have sensible names (none of this ``cat`` / ``wc``
   nonsense - apologies to you who are so trained as to think that
   ``cat`` *is* the sensible name...)
-  These names should be as close as possible to the name of the related
   function from the python library. It's ok if the function names clash
   (e.g. there's a function called ``search`` in ``re`` too), but not if
   they clash with builtin functions - in that case they get an ``s``
   prepended (hence ``sfilter``, ``sfilterfalse``, ``sformat``). (For
   discussion: is this the right idea? Would it be easier if all
   functions had s prefixes?)
-  If you need to avoid clashes, ``import streamutils as su`` (which has
   the double benefit of being nice and terse to keep your pipelines
   short, and will help make you `all powerful <xkcd.com/149/>`__)
-  Positional arguments that are central to what a function does come
   first (e.g. ``n``, the number of lines to return, is the first
   argument of ``head``) and their order should be stable over time. For
   brevity, they should be given sensible defaults. If additional
   keyword arguments are added, they will be added after existing ones.
   After the positional arguments comes ``fname``, which allows you to
   avoid using ``read``. To be safe, apart from for ``read``, ``head``,
   ``tail`` and ``follow``, ``fname`` should therefore be called as a
   keyword argument as it marks the first argument whose position is not
   guaranteed to be stable.
-  ``tokens`` is the last keyword argument of each function
-  If it's sensible for the argument to a function to be e.g. a string
   or a list of strings then both will be supported (so if you pass a
   list of filenames to ``read`` (via ``fname``), it will ``read`` each
   one in turn).
-  ``for line in open(file):`` iterates through a set of
   ``\n``-terminated strings, irrespective of ``os.linesep``, so other
   functions yielding lines should follow a similar convention (for
   example ``run`` replaces ``\r\n`` in its output with ``\n``)
-  This being the 21st century, streamutils opens files in unicode mode
   (it uses ``io.open`` in text mode). The benefits of slow-processing
   outweigh the costs. I am not opposed to adding ``readbytes`` if there
   is demand (which would return ``str`` or ``bytes`` depending on your
   python version)
-  ``head(5)`` returns the first 5 items, similarly ``tail(5)`` the last
   5 items. ``search(pattern, 2)``, ``word(3)`` and ``nth(4)`` return
   the second group, third 'word' and fourth item (not the third, fourth
   and fifth items). This therefore allows ``word(0)`` to return all
   words. Using zero-based indexing in this case feels wrong to me - is
   that too confusing/suprising? (Note that this matches how the
   coreutils behave, and besides, python is inconsistent here -
   ``group(1)`` is the first not second group, as ``group(0)`` is
   reserved for the whole pattern).

I would be open to creating a ``coreutils`` (or similarly named)
subpackage, which aims to roughly replicate the names, syntax and flags
of the ``coreutils`` toolset (i.e. ``grep``, ``cut``, ``wc`` and
friends), but only if they are implemented as thin wrappers around
streamutils functions. After all, the functionality they provide is
tried and tested, even if their names were designed primarily to be
short to type (rather than logical, memorable or discoverable).

Installation and Dependencies
-----------------------------

``streamutils`` supports python >=2.6 (on 2.6 it needs the
``OrderedDict`` and ``Counter`` backports), pypy and python >=3 by using
the `six <https://pythonhosted.org/six/>`__ library (note that >=1.4.1
is required). For now, the easiest way to install it is to pull the
latest version direct from github by running:

::

    pip install git+https://github.com/maxgrenderjones/streamutils.git

Once it's been submitted to `pypi <https://pypi.python.org/>`__, if
you've already got the dependencies installed, you'll be able to install
streamutils from `pypi <https://pypi.python.org/>`__ by running:

::

    pip install streamutils

If you want pip to install the mandatory dependencies for you, then run:

::

    pip install streamutils[deps]

And if you want to use streamutils with
`sh <https://pypi.python.org/pypi/sh>`__ or
`pbs <https://pypi.python.org/pypi/pbs>`__
(`sh <https://pypi.python.org/pypi/sh>`__ succeeded
`pbs <https://pypi.python.org/pypi/pbs>`__ which is unmaintained but
`sh <https://pypi.python.org/pypi/sh>`__ doesn't support Windows) and
want ``pip`` to install them for you (note that they just provide
syntactic sugar, not any new functionality):

::

    pip install streamutils[sh]

Note that to use them, you have to use the ``sh`` variable of the
``streamutils`` package which returns ``wrap``-ed versions of the real
``sh`` functions.

Alternatively, you can install from the source by running:

::

    python setup.py install

If you don't have
`pip <http://pip.readthedocs.org/en/latest/installing.html>`__, which is
now the official way to install python packages (assuming your package
manager isn't doing it for you) then use your package manager to install
it, or if you don't have one (hello Windows users), download and run
https://raw.github.com/pypa/pip/master/contrib/get-pip.py

Status
------

``streamutils`` is currently alpha status. By which I mean: - I think it
works fine, but the code test coverage is not yet as high as I'd like
(is it ever?) - The API is unstable, i.e. the names of functions are
still in flux, the order of the positional arguments may change, and the
order of keyword arguments is almost guaranteed to change

So why release? - Because as soon as I managed to get ``streamutils``
working, I couldn't stop thinking of all the places I'd want to use it -
Because I value feedback on the API - if you think the names of
functions or their arguments would be more easily understood if they
were changed then open an issue and let's have the debate - Because it's
a great demonstration of the crazy stuff you can do in python by
overloading operators - Why not?

How does it work?
-----------------

You don't need to know this to use the library, but you may be curious
nonetheless - if you want, you can skip this section. (Warning: this may
make your head hurt - it did mine). It's all implemented through the
python magic of duck-typing contracts, decorators, generators and
overloaded operators. (So wrong it's right? You decide...) Let's explain
it with the example of a naive pipeline designed to find module-level
function names within ``ez_setup.py``:

.. code:: python

    >>> from streamutils import *
    >>> s = read('ez_setup.py') | search(r'^def (\w+)[(]', 1) #Nothing happens yet
    >>> first_function = s | first()                          #Only now is read actually called
    >>> print(first_function)
    _python_cmd

So what happened?

In order:

-  Functions used in pipelines are expected to (optionally) take as
   input an ``Iterable`` thing (as a keyword argument called ``tokens``
   - in future, it should be possible to use any name), and use it to
   return an ``Iterable`` thing, or ``yield`` a series of values
-  Before using a function in a pipeline, it must be ``wrap``-ped (via
   the ``@wrap`` decorator). This wraps the function in a
   ``ComposableFunction`` which defers execution, so, taking ``read``
   (equivalent of unix ``cat``) as an example, if you write
   ``s=read('ez_setup.py')`` then ``read`` not actually called, but the
   ``__call__`` method of wrapping ``ComposableFunction``. This returns
   a ``ConnectingGenerator`` (which implements the basic ``generator``
   functions) which waits for something to iterate over ``s`` or to
   compose (i.e. ``|``) ``s`` with another ``ConnectingGenerator``. When
   something starts iterating over a ``ConnectingGenerator``, it passes
   through the values ``yield``-ed by the underlying function (i.e.
   ``read``). So far, so unremarkable.
-  But, and here's where the magic happens, if you ``|`` ``s`` with
   another ``wrap``-ed function e.g. ``search``, then the ``tokens``
   keyword argument of ``read`` is assigned the generator that will
   yield the output of the real ``read`` function. But still, nothing
   has happened - the functions have simply been wired together

Two options for what you do next:

-  You iterate over ``s``, in which case the functions are finally
   called and the results are passed down the chain. (Your for loop
   would iterate over the function names in ``ez_setup.py``)
-  You compose ``s`` with a function (in this case ``first``) that has
   been decorated with ``wrapTerminator`` to give a ``Terminator``
   function. A ``Terminator`` function completes the pipeline and will
   return a value, not another ``generator``. (Strictly speaking, when
   you call a ``Terminator`` nothing happens. It's only when the
   ``__or__`` function (i.e. the ``|`` or ``or`` operator) is called
   betwen a ``ConnectingGenerator`` and a ``Terminator`` that the value
   returned by the function wrapped in a ``Terminator`` - in this case
   ``first()`` is called, and the chain of generators yield their
   values.

Contribute
----------

-  Issue Tracker: http://github.com/maxgrenderjones/streamutils/issues
-  Source Code: http://github.com/maxgrenderjones/streamutils
-  API documentation: http://streamutils.readthedocs.org/
-  Continuous integration: |Build Status|
-  Test coverage: |Coverage Status|

Acknowledgements and References
-------------------------------

A shout-out goes to David Beazley, who has written the most
comprehensible (and comprehensive) documentation that I've seen on `how
to use generators <http://www.dabeaz.com/generators/>`__

Apache log file example provided by
`Nasa <http://ita.ee.lbl.gov/html/contrib/NASA-HTTP.html>`__

License
-------

The project is licensed under the `Eclipse Public License - v
1.0 <http://choosealicense.com/licenses/eclipse/>`__

.. |Build Status| image:: https://travis-ci.org/maxgrenderjones/streamutils.png
   :target: https://travis-ci.org/maxgrenderjones/streamutils/
.. |Coverage Status| image:: https://coveralls.io/repos/maxgrenderjones/streamutils/badge.png?branch=master
   :target: https://coveralls.io/r/maxgrenderjones/streamutils?branch=master
.. |Coverage Status| image:: http://coveralls.io/repos/maxgrenderjones/streamutils/badge.png?branch=master
   :target: https://coveralls.io/r/maxgrenderjones/streamutils
