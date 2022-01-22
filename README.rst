`ffmpegio`: Media I/O with FFmpeg in Python
===================================================

.. image:: https://img.shields.io/pypi/v/ffmpegio
  :alt: PyPI
.. image:: https://img.shields.io/pypi/status/ffmpegio
  :alt: PyPI - Status
.. image:: https://img.shields.io/pypi/pyversions/ffmpegio
  :alt: PyPI - Python Version
.. image:: https://img.shields.io/github/license/python-ffmpegio/python-ffmpegio
  :alt: GitHub
.. image:: https://img.shields.io/github/workflow/status/python-ffmpegio/python-ffmpegio/Run%20Tests
  :alt: GitHub Workflow Status

Python `ffmpegio` package aims to bring the full capability of `FFmpeg <https://ffmpeg.org>`__
to read, write, and manipulate multimedia data to Python. FFmpeg is an open-source cross-platform 
multimedia framework, which can handle most of the multimedia formats available today.

Main Features
-------------

* Pure-Python light-weight package interacting with FFmpeg executable found in 
  the system
* Transcode a media file to another in Python
* Read, write, filter, and create functions for audio, image, and video data
* Context-managing `ffmpegio.open` to perform stream read/write operations of video and audio
* Automatically detect and convert audio & video formats to and from `numpy.ndarray` properties
* Probe media file information
* Accepts all FFmpeg options including filter graphs
* Supports a user callback whenever FFmpeg updates its progress information file 
  (see `-progress` FFmpeg option)
* Advanced users can gain finer controls of FFmpeg I/O with `ffmpegio.ffmpegprocess` submodule
* More features to follow

Documentation
-------------

Visit our `GitHub page here <https://python-ffmpegio.github.io/python-ffmpegio/>`__
