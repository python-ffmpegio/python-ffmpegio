:py:mod:`ffmpegio`: Media I/O with FFmpeg in Python
===================================================

.. image:: https://img.shields.io/pypi/v/ffmpegio
  :alt: PyPI
.. image:: https://img.shields.io/pypi/status/ffmpegio
  :alt: PyPI - Status
.. image:: https://img.shields.io/pypi/pyversions/ffmpegio
  :alt: PyPI - Python Version
.. image:: https://img.shields.io/github/license/tikuma-lsuhsc/python-ffmpegio
  :alt: GitHub
.. image:: https://img.shields.io/github/workflow/status/tikuma-lsuhsc/python-ffmpegio/Run%20Tests
  :alt: GitHub Workflow Status

Python :py:mod:`ffmpegio` package aims to bring the full capability of `FFmpeg <https://ffmpeg.org>`__
to read, write, and manipulate multimedia data to Python. FFmpeg is an open-source cross-platform 
multimedia framework, which can handle most of the multimedia formats avilable today.

Features
--------

* Pure-Python light-weight package interacting with FFmpeg executable found in 
  the system
* A set of simple read and write functions for audio, image, and video data
* Context-managing :py:func:`ffmpegio.open` to perform stream read/write operations
* Auto-conversion of video pixel formats and audio sample formats
* Out-of-box support for fast resizing, re-orienting, cropping, rotating, and deinterlacing of video frames (all done by FFmpeg)
* More features to follow
  
.. * (planned) Audio and video filtering
.. * (planned) Multi-stream read/write


Where to start
--------------

* :ref:`Quick-start guide <quick>`

* Install via ``pip``:

.. code-block:: bash

   pip install ffmpegio

Other resources
---------------

* `GitHub project <https://github.com/tikuma-lsuhsc/python-ffmpegio>`_
* `Ask questions on the GitHub Discussion board <https://github.com/tikuma-lsuhsc/python-ffmpegio/discussions>`_
* `FFmpeg Documentation <http://ffmpeg.org/ffmpeg.html>`_
* `FFprobe Documentation <https://ffmpeg.org/ffprobe.html>`__
* `FFmpeg Filters Documentation <https://ffmpeg.org/ffmpeg-filters.html>`__
* `PyPi Project Page <https://pypi.org/project/ffmpegio/>`__


Introductory info
-----------------

.. toctree::
    :maxdepth: 1

    quick


High-level API reference
------------------------

.. toctree::
    :maxdepth: 1

    basicio
    probe
    options

Advanced topics
---------------

.. toctree::
    :maxdepth: 1

    adv-ffmpeg
    adv-args


.. .. toctree::
..     :maxdepth: 1

..     config
..     special
..     strings
..     refs
..     mpi
..     swmr
..     vds
