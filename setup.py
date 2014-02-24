#!/usr/bin/env python
#coding: utf-8
# vim: set tabstop=4 shiftwidth=4 expandtab:
from __future__ import print_function, division
import sys

from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

version=sys.version_info


deps=['six>=1.4.1']
if version.major==2 and version.minor<7:
    deps.append('ordereddict')


setup(
      name='streamutils',
      version='0.1.1', 
      package_dir = {"" : "src"},
      packages=find_packages('src'),
      extras_require = {
      	'deps': deps,
	    'sh': ['pbs'] if sys.platform=='win32' else ['sh']
      }
      )
