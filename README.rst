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

Examples
--------

.. code-block:: python

  >>> import ffmpegio

  >>> # read audio samples from 24.15 seconds to 63.2 seconds, pre-convert to mono in float data type 
  >>> fs, x = ffmpegio.audio.read('myaudio.wav', ss=24.15, to=63.2, sample_fmt='dbl', ac=1)

  >>> # read 50 video frames at t=00:32:40, pre-convert to grayscale
  >>> fs, x = ffmpegio.video.read('myvideo.mp4', ss='00:32:40', vframes=50, pix_fmt='gray')

  >>> # capture video frame at t=0.24 and resize it to 540px wide and height proportionally
  >>> # scaled with assuring even # of pixels
  >>> x = ffmpegio.image.read('myvideo.mp4', ss=0.24, s=(540,-2))

  >>> # save numpy array x as an audio file at 24000 samples/second
  >>> ffmpegio.audio.write('outputvideo.mp4', 24000, x)

  >>> # process video 100 frames at a time and save output as a new video 
  >>> # with the same frame rate
  >>> fs = ffmpegio.probe.video_streams_basic('myvideo.mp4')[0]['frame_rate']
  >>> with ffmpegio.open('myvideo.mp4', 'rv', blocksize=100) as f,
  >>>      ffmpegio.open('myoutput.mp4', 'wv', rate=fs) as g:
  >>>     for frames in f:
  >>>         g.write(myprocess(frames))

