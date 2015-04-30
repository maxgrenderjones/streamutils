API
---
.. module:: streamutils

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
 *  For now, ``#pragma: nocover`` is used to skip testing that Exceptions are thrown - these will be removed as soon as the
    normal code paths are fully tested. It is also used to skip one codepath where different code is run depending on
    which python is in use to give a correct overall coverage report
 *  Once wrapped, ComposableFunctions return a generator that can be iterated over (or if called with ``end=True``) return
    a ``list``. Terminators return things e.g. the first item in the list (see ``first``), or a ``list`` of the items in
    the stream (see ``aslist``)

.. py:function:: action(func, tokens=None)

    Calls a function for every element that passes through the stream

    :param func: function to call
    :param tokens: a list of things

.. py:function:: asdict(key=None, names=None, tokens=None)

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

.. py:function:: aslist(tokens=None)

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

.. py:function:: bag(tokens=None)

    Counts the number of occurences of each of the elements of the stream

    >>> from streamutils import *
    >>> lines = ['hi', 'ho', 'hi', 'ho', "it's", 'off', 'to', 'work', 'we', 'go']
    >>> count = matches('h.', tokens=lines) | bag()
    >>> count['hi']
    2

    :param tokens: list of items to count
    :return: A :py:class:`collections.Counter`

.. py:function:: bzread(fname=None, encoding=None, tokens=None)

    Read a file or files from bzip2-ed archives and output the lines within the files.

    >>> find('examples/NASA*.bz2') | bzread() | head(1) | write()
    199.72.81.55 - - [01/Jul/1995:00:00:01 -0400] "GET /history/apollo/ HTTP/1.0" 200 6245

    :param fname:  filename or `list` of filenames
    :param encoding: unicode encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames

.. py:function:: combine(func=None, tokens=None)

    Given a stream, combines the tokens together into a `list`. If `func` is not `None`, the `tokens` are combined 
    into a series of `list`s, chopping the `list` every time `func` returns True

    >>> ["1 2 3", "4 5 6"] | words() | separate() | smap(lambda x: int(x)+1) | combine() | write()
    [2, 3, 4, 5, 6, 7]
    >>> ["first", "line\n", "second", "line\n", "third line\n"] | combine(lambda x: x.endswith('\n')) | join(' ') | write()
    first line
    second line
    third line
    
    Note that `separate` followed by `combine` is not a no-op.
    >>> [["hello", "small"], ["world"]] | separate() | combine() | join() | write()
    hello small world

    :param tokens: a stream of things

.. py:function:: convert(converters, defaults={}, tokens=None)

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

.. py:function:: count(tokens=None)

    Counts the number of items that pass through the stream (cf ``wc -l``)

    >>> from streamutils import *
    >>> lines = ['hi', 'ho', 'hi', 'ho', "it's", 'off', 'to', 'work', 'we', 'go']
    >>> matches('h.', tokens=lines) | count()
    4

    :param tokens: Things to count
    :return: number of items in the stream as an ``int``

.. py:function:: csvread(fname=None, encoding=None, dialect='excel', n=0, names=None, skip=0, restkey=None, restval=None, tokens=None, **fmtparams)

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
    :param encoding: encoding to use to read the file (warning: the csv module in python 2 does not support unicode encoding - if you run into trouble I suggest reading the file with ``read`` then passing the output through the ``unidecode`` library using ``smap`` before ``csvread``)
    :param dialect: the csv dialect (see :py:func:`csv.reader`)
    :param n: the columns to return (starting at 1). If set, names defines the names for these columns, not the names for all columns
    :param names: the keys to use in the DictReader (see the fieldnames keyword arg of :py:func:`csv.DictReader`)
    :param skip: rows to skip (e.g. header rows) before reading data
    :param restkey: (see the restkey keyword arg of :py:func:`csv.DictReader`)
    :param restval: (see the restval keyword arg of :py:func:`csv.DictReader`)
    :param fmtparams: see :py:func:`csv.reader`

.. py:function:: csvwrite(fname=None, encoding=None, dialect='excel', names=None, restval='', extrasaction='raise', tokens=None, **fmtparams)

    Writes the stream to a file (or stdout) in csv format using :py:func:`csv.writer`. If names is set, uses a :py:func:`csv.DictWriter`

    :param fname: filename to write to - if None, uses stdout
    :param encoding: encoding to use to write the file
    :param names: the keys to use in the DictWriter

.. py:function:: dropwhile(func=None, tokens=None)

    Passes through items until the supplied function returns False (Equivalent of :py:func:`itertools.dropwhile`)

	>>> [1,2,3,2,1] | dropwhile(lambda x: x<3) | aslist()
	[3, 2, 1]

	:param func: The function to use as a predicate
	:param tokens: List of things to filter

.. py:function:: find(pathpattern=None, tokens=None)

    Searches for files the match a given pattern. For example

    >>> import os
    >>> from streamutils import find, replace, write
    >>> find('src/version.py') | replace(os.sep, '/') | write()    #Only searches src directory
    >>> find('src/*/version.py') | replace(os.sep, '/') | write()  #Searches full directory tree
    src/streamutils/version.py

    :param str pathpattern: :py:func:`glob.glob`-style pattern
    :param tokens: A list of ``glob``-style patterns to search for
    :return: An iterator across the filenames found by the function

.. py:function:: first(default=None, tokens=None)

    Returns the first item in the stream

    :param default: returned if the stream is empty
    :param tokens: a list of things
    :return: The first item in the stream

.. py:function:: firstby(keys=None, values=None, tokens=None)

    Given a series of key, value items, returns a dict of the first value assigned to each key

    >>> from streamutils import *
    >>> firsts = head(tokens=[('A', 2), ('B', 6), ('A', 3), ('C', 20), ('C', 10), ('C', 30)]) | firstby()
    >>> firsts == {'A': 2, 'B': 6, 'C': 20}
    True

    :param: keys `dict` keys for the values to aggregate on
    :params: values `dict` keys for the values to be aggregated
    :return: dict mapping each key to the first value corresponding to that key

.. py:function:: fnmatches(pathpattern, matchcase=False, tokens=None)

    Filter tokens for strings that match the pathpattern using :py:func:`fnmatch.fnmatch` or :py:func:`fnmatch.fnmatchcase`.
    Note that ``os.sep`` (i.e. ``\`` on windows) will be replaced with ``/`` to allow ``/`` to be used in the pattern

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

.. py:function:: follow(fname, encoding=None)

    Monitor a file, reading new lines as they are added (equivalent of `tail -f` on UNIX). (Note: Never returns)

    :param fname: File to read
    :param encoding: encoding to use to read the file

.. py:function:: gzread(fname=None, encoding=None, tokens=None)

    Read a file or files from gzip-ed archives and output the lines within the files.

    :param fname:  filename or `list` of filenames
    :param encoding: unicode encoding to use to open the file (if None, use platform default)
    :param tokens: list of filenames

.. py:function:: head(n=10, fname=None, skip=0, encoding=None, tokens=None)

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

.. py:function:: join(sep=' ', tokens=None)

    Joins a list-like thing together using the supplied `sep` (think :py:func:`str.join`). Defaults to joining with a space

    >>> split(sep=',', n=[1,4], tokens=['flopsy,mopsy,cottontail,peter']) | join(',') | write()
    flopsy,peter

    :param sep: string separator to use to join each line in the stream (default ' ')

.. py:function:: last(default=None, tokens=None,)

    Returns the final item in the stream

    :param default: returned if the stream is empty
    :param tokens: a list of things
    :return: The last item in the stream

.. py:function:: lastby(keys=None, values=None, tokens=None)

    Given a series of key, value items, returns a dict of the last value assigned to each key

    >>> from streamutils import *
    >>> lasts = head(tokens=[('A', 2), ('B', 6), ('A', 3), ('C', 20), ('C', 10), ('C', 30)]) | lastby()
    >>> lasts == {'A': 3, 'B': 6, 'C': 30}
    True

    :return: dict mapping each key to the last value corresponding to that key

.. py:function:: matches(pattern, match=False, flags=0, v=False, tokens=None)

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

.. py:function:: meanby(keys=None, values=None, tokens=None)

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

    :param: keys `dict` keys for the values to aggregate on
    :params: values `dict` keys for the values to be aggregated
    :return: dict mapping each key to the sum of all the values corresponding to that key

.. py:function:: nlargest(n, key=None, tokens=None)

    Returns the n largest elements of the stream (see documentation for :py:func:`heapq.nlargest`)

    >>> from streamutils import *
    >>> head(10, tokens=range(1,10)) | nlargest(4)
    [9, 8, 7, 6]

.. py:function:: nomatch(pattern, match=False, flags=0, tokens=None)

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

.. py:function:: nsmallest(n, key=None, tokens=None)

    Returns the n smallest elements of the stream (see documentation for :py:func:`heapq.nsmallest`)

    >>> from streamutils import *
    >>> head(10, tokens=range(1,10)) | nsmallest(4)
    [1, 2, 3, 4]

.. py:function:: nth(n, default=None, tokens=None)

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

.. py:function:: read(fname=None, encoding=None, skip=0, tokens=None)

    Read a file or files and output the lines it contains. Files are opened with :py:func:`io.read`

    >>> from streamutils import *
    >>> read('https://raw.github.com/maxgrenderjones/streamutils/master/README.md') | search('^[-] Source Code: (.*)', 1) | write()
    http://github.com/maxgrenderjones/streamutils

    :param fname: filename or `list` of filenames. Can either be paths to local files or URLs (e.g. http:// or ftp:// - supports the same protocols as :py:func:`urllib2.urlopen`)
    :param encoding: encoding to use to open the file (if None, use platform default)
    :param skip: number of lines to skip at the beginning of each file
    :param tokens: list of filenames

.. py:function:: replace(old, new, tokens=None)

    Replace ``old`` in each tokens with ``new`` via call to ``.replace`` on each token (e.g. :py:func:`str.replace`)

    :param old: text to replace
    :param new: what to replace it with
    :param tokens: typically a series of strings

.. py:function:: run(command, err=False, cwd=None, env=None, tokens=None)

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

.. py:function:: separate(tokens=None)

    Takes a stream of `Iterable`s, and yields items from the iterables 

    >>> [["hello", "there"], ["how", "are"], ["you"]] | separate() | write()
    hello
    there
    how
    are
    you

    :param tokens: a stream of Iterables

.. py:function:: sfilter(func=None, tokens=None)

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

.. py:function:: sfilterfalse(func=None, tokens=None)

    Passes through items for which the output of the filter function is False in a boolean context

    >>> sfilterfalse(lambda x: x.endswith('ball'), tokens=['football', 'rugby', 'tennis', 'volleyball']) | write()
    rugby
    tennis

    :param filterfunction: Function to use for filtering
    :param tokens: List of things to filter

.. py:function:: sformat(pattern, tokens=None)

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

.. py:function:: smap(*funcs, **kwargs)

    Applies a transformation function to each element of the stream (or series of function). Note that `smap(f, g, tokens)` yields f(g(token))`

    >>> from streamutils import *
    >>> smap(str.upper, tokens=['aeiou']) | write()
    AEIOU
    >>> smap(str.upper, str.strip, str.lower, tokens=[' hello ', ' world ']) | write()
    HELLO
    WORLD

    :param *funcs: functions to apply
    :param tokens: list/iterable of objects

.. py:function:: smax(key=None, tokens=None)

    Returns the largest item in the stream

    >>> from streamutils import *
    >>> dates = ['2014-01-01', '2014-02-01', '2014-03-01']
    >>> head(tokens=dates) | smax()
    '2014-03-01'

    :param key: See documentation for :py:func:`max`
    :param tokens: a list of things
    :return: The largest item in the stream (as defined by python :py:func:`max`)

.. py:function:: smin(key=None, tokens=None)

    Returns the smallest item in the stream

    >>> from streamutils import *
    >>> dates = ['2014-01-01', '2014-02-01', '2014-03-01']
    >>> head(tokens=dates) | smin()
    '2014-01-01'

    :param key: See documentation for :py:func:`min`
    :param tokens: a list of things
    :return: The largest item in the stream (as defined by python :py:func:`min`)

.. py:function:: split(n=0, sep=None, outsep=None, names=None, inject={}, tokens=None)

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

.. py:function:: sreduce(func, initial=None, tokens=None)

    Uses a function to :py:func:`reduce` the output to a single value

    :param func: Function to use in the reduction
    :param initial: An initial value
    :return: Output of the reduction

.. py:function:: sslice(start=1, stop=None, step=1, fname=None, encoding=None, tokens=None)

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

.. py:function:: ssorted(cmp=None, key=None, reverse=False, tokens=None)

    Sorts the output of the stream (see documentation for :py:func:`sorted`). Warning: ``cmp`` was removed from ``sorted``
    in python 3

    >>> from streamutils import *
    >>> for line in (find('*.py') | replace(os.sep, '/') | ssorted()):
    ...     print(line)
    ez_setup.py
    setup.py

    :return: a sorted list

.. py:function:: ssum(start=0, tokens=None)

    Adds the items that pass through the stream via call to :py:func:`sum`
    
    >>> from streamutils import *
    >>> head(tokens=[1,2,3]) | ssum()
    6

    :param start: Initial value to start the sum, returned if the stream is empty
    :return: sum of all the values in the stream

.. py:function:: strip(chars=None, tokens=None)

    Runs ``.strip`` against each line of the stream

    >>> from streamutils import *
    >>> line=strip(tokens=['  line\n']) | first()
    >>> line=='line'
    True

    :param tokens: A series of lines to remove whitespace from

.. py:function:: sumby(keys=None, values=None, tokens=None)

    If keys and values are not set, given a series of key, value items, returns a dict of summed values, grouped by key
    
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

.. py:function:: tail(n=10, fname=None, encoding=None, tokens=None)

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

.. py:function:: takewhile(func=None, tokens=None)

    Passes through items until the supplied function returns False (Equivalent of :py:func:`itertools.takewhile`)

	>>> [1,2,3,2,1] | takewhile(lambda x: x<3) | aslist()
	[1, 2]

	:param func: The function to use as a predicate
	:param tokens: List of things to filter

.. py:function:: traverse(tokens=None)

    Performs a full depth-first unwrapping of the supplied tokens. Strings are **not** unwrapped
    >>> ["hello", ["hello", [["world"]]]] | traverse() | join() | write()
    hello
    hello world

.. py:function:: unique(tokens=None)

    Passes through values the first time they are seen

    >>> from streamutils import *
    >>> lines=['one', 'two', 'two', 'three', 'three', 'three', 'one']
    >>> unique(lines) | write()
    one
    two
    three

    :param tokens: Either set by the pipeline or provided as an initial list of items to pass through the pipeline

.. py:function:: unwrap(tokens=None)

    Yields a stream of `list`s, with one level of nesting in the tokens the stream unwrapped (if present).

    >>> [[[1], [2]], [[2, 3, 4], [5]], [[[6]]]] | unwrap() | write()
    [1, 2]
    [2, 3, 4, 5]
    [[6]]

    :param tokens: a stream of Iterables

.. py:function:: update(values=None, funcs=None, tokens=None)

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

.. py:function:: words(n=0, word=r'\S+', outsep=None, names=None, inject=None, flags=0, tokens=None)

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

.. py:function:: write(fname=None, encoding=None, tokens=None)

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
