Tutorial and cookbook
=====================

Parsing an Apache logfile
-------------------------

Suppose we have an apache log file we want to extract info from. (Note that the logfile used here is pretty old, so won't necessarily be in the same format as any log files you may have on your own servers. Let's have a look at the file to see what the contents look like:

..doctest::

    >>> from __future__ import print_function, unicode_literals
    >>> from streamutils import *
    >>> import os
    >>> logfile = find('examples/*log.bz2') | first()
    >>> print(logfile.replace(os.sep, '/'))
    examples/NASA_access_log_July95.log.bz2
    >>> bzread(fname=logfile) | head(5) | write()
    199.72.81.55 - - [01/Jul/1995:00:00:01 -0400] "GET /history/apollo/ HTTP/1.0" 200 6245
    unicomp6.unicomp.net - - [01/Jul/1995:00:00:06 -0400] "GET /shuttle/countdown/ HTTP/1.0" 200 3985
    199.120.110.21 - - [01/Jul/1995:00:00:09 -0400] "GET /shuttle/missions/sts-73/mission-sts-73.html HTTP/1.0" 200 4085
    burger.letters.com - - [01/Jul/1995:00:00:11 -0400] "GET /shuttle/countdown/liftoff.html HTTP/1.0" 304 0
    199.120.110.21 - - [01/Jul/1995:00:00:11 -0400] "GET /shuttle/missions/sts-73/sts-73-patch-small.gif HTTP/1.0" 200 4179

So, suppose we want to see who's accessing us most, we can pick out the relevant hostnames with ``search`` and then use ``bag`` to count them

..doctest::

    >>> logpattern=r'^([\w.-]+)'
    >>> clients = bzread(fname=logfile) | search(logpattern) | bag()
    >>> fan = clients.most_common()[0]
    >>> print('%s accessed us %d times' % (fan[0], fan[1]))
    kristina.az.com accessed us 118 times


Nesting streams to filter for files based on content
----------------------------------------------------

Suppose we want to find python source files that don't use ``/usr/bin/env`` to call python. We can't do this in a normal pipeline, as we want the names of the files, not their content. To do this, we need to make a nested pipeline like so::

..doctest::

    >>> import shutil, tempfile, os.path
    >>> try:
    ...     d=tempfile.mkdtemp()
    ...     #First do some setup
    ...     with open(os.path.join(d, 'envpython.py'), 'w') as f: #
    ...         w=f.write('#!/usr/bin/env python')
    ...     with open(os.path.join(d, 'python2.7.py'), 'w') as f:
    ...         w=f.write('#!/usr/bin/python2.7')
    ...     #Now look for the files
    ...     find('%s/*.py' % d) | sfilter(lambda x: read(x) | nomatch('/usr/bin/env') | first()) | transform(os.path.basename) | write()
    ... finally:
    ...     shutil.rmtree(d)
    python2.7.py


Getting the correct function signatures in sphinx for decorated methods
-----------------------------------------------------------------------

Context: the problem with python generators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Decorators in python are a good thing |trade|, and writing something like ``streamutils`` would be impossible without them.. However, unless you use the `decorator <https://pypi.python.org/pypi/decorator>`__ module, even if you use :py:func:`functools.update_wrapper` or :py:func:`functools.wraps`, the wrapped function signatures are lost, and so appear as ``dosomething(...)`` in documentation, not ``dosomething(arg1, arg2='default')``. Fortunately, it is possible to tell the `autodoc <http://sphinx-doc.org/ext/autodoc.html>`__ plugin for ``sphinx`` to insert the correct signature, but you need to supply it in your documentation. So suppose you want ``autodoc`` to pull in all the docstrings of the ``Noodle`` module for you, you might use::

    .. autoclass:: Noodle
       :members:

In order to generate the documentation for a ``Noodle`` class and supply the correct function signatures, you now need to write::

    .. autoclass:: Noodle(type)
       .. automethod:: eat(persona)

Solution: Autogenerating output from a source file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Problem is, you now need to maintain your method signature documentation in two places. One potential solution (that streamutils itself uses) is to autogenerate this output like so::

..doctest::

    >>> import streamutils as su
    >>> from streamutils import *
    >>> funcs=read(fname='src/streamutils/__init__.py') | search(r'\s?def ((\w+)[(].*[)]):(?:\s?[#].*)?', group=None, names=['sig', 'name']) | sfilter(lambda x: x['name'] in (set(su.__all__) - set(['wrap', 'wrapTerminator']))) | ssorted(key=lambda x: x['name'])
    >>> with open('docs/api.rst', 'w') as apirst:
    ...     lines=[]
    ...     lines.append('API\n')
    ...     lines.append('---\n')
    ...     lines.append('.. automodule:: streamutils\n')
    ...     lines.append('    :members: \n')
    ...     lines.extend(['    .. automethod:: %s\n' % f['sig'] for f in funcs])
    ...     apirst.writelines(lines)
    ...
    >>> head(7, fname='docs/api.rst') | write()
    API
    ---
    .. automodule:: streamutils
        :members:
        .. automethod:: action(func, tokens=None)
        .. automethod:: asdict(key=None, names=None, tokens=None)
        .. automethod:: aslist(tokens=None)

.. include:: <isonum.txt>