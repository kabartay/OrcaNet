#!/usr/bin/env python
from setuptools import setup, find_packages
from pkg_resources import get_distribution, DistributionNotFound

with open('requirements.txt') as fobj:
    requirements = [l.strip() for l in fobj.readlines()]

setup(
    name='orcanet',
    description='Runs Neural Networks for usage in the KM3NeT project',
    url='https://git.km3net.de/ml/OrcaNet',
    version='1.0',
    author='Michael Moser, Stefan Reck',
    author_email='mmoser@km3net.de, michael.m.moser@fau.de, stefan.reck@fau.de',
    license='AGPL',
    install_requires=requirements,
    packages=find_packages(),
    include_package_data=True,

    # setup_requires=['setuptools_scm'],
    # use_scm_version={
    #     'write_to': 'orcanet/version.txt',
    #     'tag_regex': r'^(?P<prefix>v)?(?P<version>[^\+]+)(?P<suffix>.*)?$',
    # },
    # classifiers=[
    #     'Development Status :: 3 - Alpha',
    #     'Intended Audience :: Developers',
    #     'Intended Audience :: Science/Research',
    #     'Programming Language :: Python',
    #]
)

__author__ = 'Michael Moser and Stefan Reck'