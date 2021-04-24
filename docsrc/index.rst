ffmpegio Python Package: Media File I/O with FFmpeg
===================================================

.. toctree::
   :maxdepth: 2

   get_started
   api
   options

| PyPi: `<https://pypi.org/project/ffmpegio/>`__
| GitHub: `<https://github.com/tikuma-lsuhsc/python-ffmpegio>`__

.. warning::
   This package is still in an early alpha stage and under heavy consturction.

Introduction
============

`FFmpeg <https://ffmpeg.org>`__ is an open-source cross-platform multimedia 
framework, and Python :py:mod:`ffmpegio` package utilizes it to read, write, and
manipulate multimedia data.

Main Features
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
* (planned) Audio and video filtering
* (planned) Multi-stream read/write

