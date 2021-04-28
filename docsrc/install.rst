Getting Started with ffmpegio
=============================

| PyPi: `<https://pypi.org/project/ffmpegio/>`__
| GitHub: `<https://github.com/tikuma-lsuhsc/python-ffmpegio>`__

.. warning::
   This package is still in an early alpha stage and under heavy consturction.

Installation
^^^^^^^^^^^^

To use :py:mod:`ffmpegio`, the package must be installed on Python as well as  
having the FFmpeg binary files in a location :py:mod:`ffmpegio` can find.

Install the :py:mod:`ffmpegio` package via ``pip``:

.. code-block:: bash

   pip install ffmpegio

The installation of FFmpeg is platform dependent. For Ubuntu,

.. code-block:: bash

   sudo apt install ffmpeg

and Mac,

.. code-block:: bash

   brew install ffmpeg

no other actions are needed as these commands will place the FFmpeg executables 
on the system path. For Windows, it is a bit more complicated.

1. Download pre-built packages from the links available on the `FFmpeg's Download page
   <https://ffmpeg.org/download.html#build-windows>`__.
2. Unzip the content and place the files on one of the following directories:

   ==================================  ===============================================
   Auto-detectable FFmpeg folder path  Example
   ==================================  ===============================================
   ``%PROGRAMFILES%\ffmpeg``           ``C:\Program Files\ffmpeg``
   ``%PROGRAMFILES(X86)%\ffmpeg``      ``C:\Program Files (x86)\ffmpeg``
   ``%USERPROFILE%\ffmpeg``            ``C:\Users\john\ffmpeg``
   ``%APPDATA%\ffmpeg``                ``C:\Users\john\AppData\Roaming\ffmpeg``
   ``%APPDATA%\programs\ffmpeg``       ``C:\Users\john\AppData\Roaming\programs\ffmpeg``
   ``%LOCALAPPDATA%\ffmpeg``           ``C:\Users\john\AppData\Local\ffmpeg``
   ``%LOCALAPPDATA%\programs\ffmpeg``  ``C:\Users\john\AppData\Local\programs\ffmpeg``
   ==================================  ===============================================

   Keep the internal structure intact, i.e., the executables must be found at 
   ``ffmpeg\bin\ffmpeg.exe`` and ``ffmpeg\bin\ffprobe.exe``.

   Alternately, the FFmpeg may be placed elsewhere and use :py:func:`ffmpegio.set_path` to
   specify the location.

Setting up your Python code
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import ffmpegio



Reading/writing audio files
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # read the entire file
   fs, x = ffmpegio.audio.read('my_audio.mp3')

   # read only the first 3 seconds
   fs, x = ffmpegio.audio.read('my_audio.mp3', duration=3.0)

   # read data between 1 and 5 second marks
   fs, x = ffmpegio.audio.read('my_audio.mp3', start=1.0, end=5.0)

.. code-block:: python

   import numpy as np

   fs = 44100
   T = 1.0
   t = np.arange(int(T * fs))

   dtype = np.int16  # 16-bit audio data
   vol = 0.8 * np.iinfo(dtype).max  # 80% of full-volume

   # write 1-second FLAC file with middle-A tone
   f0 = 440
   x = vol * np.cos(2 * np.pi * f0 * t)

   ffmpegio.audio.write("my_audio.flac", fs, x.astype(dtype))

   # add second channel with high-E tone
   f1 = f0 * np.log(7) / np.log(12)
   y = vol * np.cos(2 * np.pi * f0 * t)

   xy = np.stack((x, y), axis=1)
   ffmpegio.audio.write("my_audio.wav", fs, xy.astype(dtype))



Examples
--------

Read entire audio file

Read 10 video frames

Read an image