#!/usr/bin/env python

from distutils.core import setup

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='asyncjson',
    description='Asynchronous json library with support of nested awaitable objects in data',
    version='0.0.1',
    author='Igor Derkach',
    author_email='gosha753951@gmail.com',
    url='https://github.com/bdragon300/asyncjson',
    license='Apache 2.0',
    python_requires='>=3.6',
    packages=setuptools.find_packages(exclude=['tests']),
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Software Development :: Libraries'
    ],
)
