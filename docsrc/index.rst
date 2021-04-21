Python Package: ffmpegio --- Media File I/O with FFmpeg
=======================================================

.. toctree::
   :maxdepth: 2

| PyPi: `<https://pypi.org/project/ffmpegio/>`__
| GitHub: `<https://github.com/tikuma-lsuhsc/python-ffmpegio>`__

Introduction
------------

`FFmpeg <https://ffmpeg.org>`__ is an open-source cross-platform multimedia framework to "decode, 
encode, transcode, mux, demux, stream, filter and play pretty much anything that humans and machines 
have created." Python :py:mod:`ffmpegio` package is (yet another) FFmpeg wrapper to enable reading 
and writing media data with a future roadmap to include filtering and other convenience features.

Installation
------------

Install the package via pip:

.. code-block:: bash

   pip install ffmpegio

Examples
--------

Read entire audio file

Read 10 video frames

Read an image



Package Contents
----------------
.. autofunction:: ffmpegio.open
.. autofunction:: ffmpegio.transcode

.. autofunction:: ffmpegio.video.read
.. autofunction:: ffmpegio.video.write
.. autofunction:: ffmpegio.audio.read
.. autofunction:: ffmpegio.audio.write
.. autofunction:: ffmpegio.image.read
.. autofunction:: ffmpegio.image.write

.. autofunction:: ffmpegio.set_path