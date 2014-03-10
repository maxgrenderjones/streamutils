#!/usr/bin/env python
#coding: utf-8
# vim: set tabstop=4 shiftwidth=4 expandtab:
from __future__ import print_function, division
import sys, os.path

if os.path.exists('ez_setup.py'):
    from ez_setup import use_setuptools
    use_setuptools()

from setuptools import setup, find_packages
from distutils.command import build

version=sys.version_info

deps=['six>=1.4.1']
if version[0]==2 and version[1] < 7:  # version_info is a tuple in python2.6
    deps.append('ordereddict')
    deps.append('counter')


setup(
    name='streamutils',
    version='0.1.1',
    package_dir={"": "src"},
    packages=find_packages('src'),
    extras_require={
        'deps': deps,
        'sh': deps +
              (['pbs'] if sys.platform=='win32' else ['sh'])
    }
)
