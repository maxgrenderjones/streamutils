Testing streamutils
===================

Writing tests
-------------
streamutils contains tests at three levels:

inline doctests
    doctest_-style tests are used within the source files to give a basic demonstration of how each function can be used

documentation doctests
    To allow for more involved options, `doctest`_-style tests are also used within the documentation to improve test coverage and ensure documentation does not become out of date

boring and bugfix tests
   Not all tests are informative (particularly those checking that an exception is raised when expected or regression tests). These are implemented using `py.test`_ and can be found in the ``test`` directory of the source tree.

The aim is to achieve 100% test coverage across the three differet test types. New features should be accompanied by tests to show what they do, and bug fixes should be accompanied by tests to ensure things stay fixed!

Running tests
-------------
Testing using the current python version
________________________________________
In order to run the tests for streamutils and pick up all the relevant types of tests a rather involved invocation of py.test_ is required. This has been integrated into ``setup.py``, so all you need to do to run the tests on your current version of python is run ``python setup.py test``

Testing against supported python versions
_________________________________________
streamutils supports pypy and python versions >=2.6. To test that any changes don't break anything on any of these versions, you can use tox_, which will test a clean install of streamutils in a virtualenv_ using each of the supported pythons (so long as you have them set up on your system). All you need to do is run ``tox``. (Internally, for each supported python this configures the environment appropriately, installs dependencies and calls ``python setup.py test``)

Continuous integration
______________________
Because it's easy to forget to run tests and to keep the test coverage reports up to date, streamutils uses travis_ to run integration testing after every push to the github repository (it just calls ``tox`` and then ``coveralls`` to upload the test coverage status to coveralls_).


.. _doctest: http://docs.python.org/2/library/doctest.html
.. _`py.test`: http://pytest.org/
.. _tox: https://testrun.org/tox/
.. _virtualenv: http://www.virtualenv.org/
.. _travis: http://travis-ci.org/
.. _coveralls: http://coveralls.io/