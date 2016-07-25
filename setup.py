#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='WRTMTester',
    version='0.1',
    description='Master testing app orchestrating WRTMasher modules on a remote DUT',
    author='Marcin Dziezyc',
    author_email='yakcyll@gmail.com',
    packages=['wrtmtester'],
    package_dir={'wrtmtester': 'src/wrtmtester'},
    install_requires=['pyserial'],
)
