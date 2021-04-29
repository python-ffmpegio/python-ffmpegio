.. _quick:

Quick Start Guide
=================

Install
-------

To use :py:mod:`ffmpegio`, the package must be installed on Python as well as  
having the FFmpeg binary files at a location :py:mod:`ffmpegio` can find.

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
2. Unzip the content and place the files in one of the following directories:

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
   specify any arbitrary location.

Core offerings
--------------

FFmpeg can read/write virtually any multimedia file out there, and :code:`ffmpegio` uses 
the FFmpeg's prowess to perform media I/O (and other) operations in Python. It offers two
basic modes of operation: block read/write and stream read/write. Another feature of 
:code:`ffmpegio` is to report the properties of the media files, using FFprobe.

Media Probe
-----------

To process a media file, you first need to know what's in it. Within FFmpeg
ecosystem, this task is handled by `ffprobe<https://ffmpeg.org/ffprobe.html>`__.
:code:`ffmpegio` offers a wrapper module :ref:`ffmpegio:probe<probe>` with 4
basic functions:: 

    >>> import ffmpegio
    >>> from pprint import pprint
    >>> url = 'mytestvideo.mpg'
    >>> format_info = ffmpegio.probe.format_basic(url)
    >>> pprint(format_info)
    {'duration': 66.403256,
    'filename': 'mytestvideo.mpg',
    'format_name': 'mpegts',
    'nb_streams': 2,
    'start_time': 0.0}
    >>> stream_info = ffmpegio.probe.streams_basic(url)
    >>> pprint(stream_info) 
    [{'codec_name': 'mp2', 'codec_type': 'audio', 'index': 0},
    {'codec_name': 'h264', 'codec_type': 'video', 'index': 1}]
    >>> vst_info =ffmpegio.probe.video_streams_basic(url) 
    >>> pprint.pprint(vst_info) 
    [{'codec_name': 'h264',
    'display_aspect_ratio': Fraction(22, 15),
    'duration': 66.39972222222222,
    'frame_rate': Fraction(15000, 1001),
    'height': 240,
    'index': 1,
    'pix_fmt': 'yuv420p',
    'sample_aspect_ratio': Fraction(1, 1),
    'start_time': 0.0,
    'width': 352}]
    >>> ast_info = ffmpegio.probe.audio_streams_basic(url)
    >>> pprint.pprint(ast_info) 
    [{'channel_layout': 'stereo',
    'channels': 2,
    'codec_name': 'mp2',
    'duration': 66.40325555555556,
    'index': 0,
    'nb_samples': 2928384,
    'sample_fmt': 'fltp',
    'sample_rate': 44100,
    'start_time': 0.0}]

To obtain the complete ffprobe output, use :py:func:`ffmpegio.probe.inquire`. For more information, 
see :ref:`probe`.

Block Read/Write
----------------

Suppose you need to analyze short audio data in :code:`mytestfile.mp3`, you can
read all its samples by::

    >>> fs, x = ffmpegio.audio.read('mytestfile.wav')

It returns the sampling rate :code:`fs` and :py:class:`numpy.ndarray` :code:`x`. 
The audio data is always represetned by a 2-D array, each of which column represents
an audio channel. So, a 2-second stereo recording at 8000 samples/second yields
:code:`x.shape` to be :code:`(16000,2)`. Also, the sample format is preserved: If
the samples in the wav file is 16-bit, :code:`x` is of :code:`numpy.int16` dtype.

Now, you've processed this audio data and produced the 8000-sample 1-D array :code:`y`
at reduced sampling rate at 4000-samples/second. You want to save this new audio 
data as FLAC file. To do so, you run::

    >>> ffmpegio.audio.write('myoutput.flac', 4000, y)

There are video counterparts to these two functions:

    >>> fs, F = ffmpegio.video.read('mytestvideo.mp4')
    >>> ffmpegio.video.write('myoutput.avi', fs, F)

Let's suppose :code:`mytestvideo.mp4` is 10 seconds long, containing a 
:code:`yuv420p`-encoded color video stream with the frame size of 640x480 pixels,
and the frame rate of 29.97 (30000/1001) frames/second. Then, the :py:func:`video.read`
returns a 2-element tuple: the first element :code:`fs` is the frame rate in 
:py:class:`fractions.Fraction` and the second element :code:`F` contains all the frames
of the video in :py:class:`numpy.ndarray` with shape :code:`(299, 480, 640, 3)`.
Because the video is in color, each pixel is represented in 24-bit RGB, thus
:code:`F.dtype` is :code:`numpy.uint8`. The video write is the reciprocal of
the read operation.

For image (or single video frame) I/O, there is a pair of functions as well::

    >>> I = ffmpegio.image.read('myimage.png')
    >>> ffmpegio.image.write('myoutput.bmp', I)

The image data :code:`I` is like the video frame data, but without the leading
dimension.

Stream Read/Write
-----------------

Block read/write is simple and convenient for a short file, but it quickly 
becomes slow and inefficient as the data size grows; this is especially true 
for video. To enable on-demand data retrieval, :code:`ffmpegio` offers stream
read/write operation. It mimics the familiar Python's file I/O with 
:py:func:`ffmpegio.open()`::

    >>> with ffmpegio.open("mytestvideo.mp4", 'v') as f: # opens the first video stream
    >>>     print(f.frame_rate) # frame rate fraction in frames/second
    >>>     F = f.read() # read the first frame
    >>>     F = f.read(5) # read the next 5 frames at once

Another example, which uses read and write streams simultaneously::

    >>> with ffmpegio.open("mytestvideo.mp4", 'rv') as f:
    >>>     with ffmpegio.open("myoutput.avi", "wv", f.frame_rate) as g:
    >>>         for frame in f.readiter(): # iterates over all frames, one at a time
    >>>             output = my_processor(frame) # function to process data
    >>>             g.write(output) # send the processed frame to 'myoutput.avi' 

By default, :code:`ffmpegio.open()` opens the first media stream availble to read.
However, the operation mode can be specified via the :code:`mode` second argument.
The above example, opens :code:`mytestvideo.mp4` file in :code:`"rv"` or "read 
video" mode and :code:`myoutput.avi` in :code:`"wv"` or "write video" mode. The 
file reader object :code:`f` is equipped with :code:`read()` method while the 
write object comes with :code:`write()` method. The reader, in addition, has
:code:`readiter()` generator to iterate as long as there are data to read. For more, 
see :py:func:`ffmpegio.open`.

