#!/usr/bin/env python

from distutils.core import setup

setup(
    name='WRTM-Tester',
    version='0.1',
    description='Master testing app orchestrating WRTMasher modules on a remote DUT',
    author='Marcin Dziezyc',
    author_email='yakcyll@gmail.com',
    packages=['timeout-decorator', 'pyping'],
)
