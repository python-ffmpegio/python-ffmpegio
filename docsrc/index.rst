ffmpegio Python Package: Media File I/O with FFmpeg
===================================================

.. warning::
   This package is still in an early alpha stage and under heavy consturction.

`FFmpeg <https://ffmpeg.org>`__ is an open-source cross-platform multimedia 
framework, and Python :py:mod:`ffmpegio` package utilizes it to read, write, and
manipulate multimedia data.

Features
-------------

* Pure-Python light-weight package interacting with FFmpeg executable found in 
  the system
* A set of simple read and write functions for audio, image, and video data
* Context-managing :py:func:`ffmpegio.open` to perform frame-wise read/write
  operations
* Auto-conversion of video pixel formats to RGB/grayscale formats with/without 
  transparency alpha channel
* Out-of-box support for fast resizing, re-orienting, cropping, and 
  deinterlacing of video frames (all done by FFmpeg)
  
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

* `FFmpeg Documentation <http://ffmpeg.org/ffmpeg.html>`_
* `Ask questions on the GitHub Discussion board <https://github.com/tikuma-lsuhsc/python-ffmpegio/discussions>`_
* `GitHub project <https://github.com/tikuma-lsuhsc/python-ffmpegio>`_
* `PyPi page <https://pypi.org/project/ffmpegio/>`_


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

TBD

.. .. toctree::
..     :maxdepth: 1

..     config
..     special
..     strings
..     refs
..     mpi
..     swmr
..     vds
