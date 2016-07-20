#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='WRTM-Tester',
    version='0.1',
    description='Master testing app orchestrating WRTMasher modules on a remote DUT',
    author='Marcin Dziezyc',
    author_email='yakcyll@gmail.com',
    packages=find_packages(),
    install_requires=['timeout-decorator', 'pyping'],
)
