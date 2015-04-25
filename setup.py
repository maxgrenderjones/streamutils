#!/usr/bin/env python
#coding: utf-8
# vim: set tabstop=4 shiftwidth=4 expandtab:
from __future__ import print_function, division
import sys, os.path, multiprocessing #multiprocessing needed for bug workaround (http://bugs.python.org/issue15881#msg170215)

try:
    from setuptools import setup, find_packages
    from setuptools.command.test import test as TestCommand
except:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages
    from setuptools.command.test import test as TestCommand

from distutils.command import build

version=sys.version_info

class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = '--doctest-modules --cov src --cov-report term-missing --doctest-glob=*.rst --ignore setup.py --ignore docs/conf.py --ignore docs/api.rst'.split()
        self.test_suite = True
    def run_tests(self):
        #import here, 'cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src','streamutils','version.py')).read())
deps=['six>=1.4.1', 'setuptools']
if version[0]==2 and version[1] < 7:  # version_info is a tuple in python2.6
    deps.append('ordereddict')
    deps.append('counter')
shdeps=['pbs'] if sys.platform=='win32' else ['sh']
lzmadeps=['backports.lzma'] if (version[0]<3 or version[1]<3) else []

setup(
    name='streamutils',
    keywords='UNIX pipelines for python',
    description=('Pythonic implementation of UNIX-style pipelines'),
    url='http://streamutils.readthedocs.org/en/latest/',
    author='Max Grender-Jones',
    author_email='MaxGrenderJones@gmail.com',
    version=__version__,
    package_dir={"": "src"},
    packages=find_packages('src'),
    extras_require={
        'deps': deps,
        'sh': deps + shdeps,
        'lzma': deps + lzmadeps,
    },
    tests_require=deps+shdeps+lzmadeps+['pytest>=2.3.4', 'pytest-cov'],
    cmdclass = {'test': PyTest},
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.rst')).read(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Utilities',
        'Topic :: Text Processing',
#       'Operating System :: OS Independent'
    ]
)

