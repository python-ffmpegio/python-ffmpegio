.. _quick:
.. highlight:: python

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

Features
--------

FFmpeg can read/write virtually any multimedia file out there, and :code:`ffmpegio` uses 
the FFmpeg's prowess to perform media I/O (and other) operations in Python. It offers two
basic modes of operation: block read/write and stream read/write. Another feature of 
:code:`ffmpegio` is to report the properties of the media files, using FFprobe.

Media Probe
-----------

To process a media file, you first need to know what's in it. Within FFmpeg
ecosystem, this task is handled by `ffprobe <https://ffmpeg.org/ffprobe.html>`__.
:code:`ffmpegio`'s :ref:`ffmpegio:probe<probe>` module wraps ffprobe with 4
basic functions:

.. code-block:: python

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

    >>> vst_info = ffmpegio.probe.video_streams_basic(url) 
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

To obtain the complete ffprobe output, use :py:func:`ffmpegio.probe.full_details`. 
For more information on :py:mod:`probe`, see :ref:`probe`.

Block Read/Write
----------------

Suppose you need to analyze short audio data in :code:`mytestfile.mp3`, you can
read all its samples by

.. code-block:: python

    >>> fs, x = ffmpegio.audio.read('mytestfile.wav')

It returns the sampling rate :code:`fs` and :py:class:`numpy.ndarray` :code:`x`. 
The audio data is always represetned by a 2-D array, each of which column represents
an audio channel. So, a 2-second stereo recording at 8000 samples/second yields
:code:`x.shape` to be :code:`(16000,2)`. Also, the sample format is preserved: If
the samples in the wav file is 16-bit, :code:`x` is of :code:`numpy.int16` dtype.

Now, you've processed this audio data and produced the 8000-sample 1-D array :code:`y`
at reduced sampling rate at 4000-samples/second. You want to save this new audio 
data as FLAC file. To do so, you run:

.. code-block:: python

    >>> ffmpegio.audio.write('myoutput.flac', 4000, y)

There are video counterparts to these two functions:

.. code-block:: python

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

For image (or single video frame) I/O, there is a pair of functions as well:

.. code-block:: python

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
:py:func:`ffmpegio.open()`:

.. code-block:: python

    >>> with ffmpegio.open('mytestvideo.mp4', 'v') as f: # opens the first video stream
    >>>     print(f.frame_rate) # frame rate fraction in frames/second
    >>>     F = f.read() # read the first frame
    >>>     F = f.read(5) # read the next 5 frames at once

Another example, which uses read and write streams simultaneously:

.. code-block:: python

    >>> with ffmpegio.open('mytestvideo.mp4', 'rv') as f:
    >>>     with ffmpegio.open('myoutput.avi', 'wv', f.frame_rate) as g:
    >>>         for frame in f.readiter(): # iterates over all frames, one at a time
    >>>             output = my_processor(frame) # function to process data
    >>>             g.write(output) # send the processed frame to 'myoutput.avi' 

By default, :code:`ffmpegio.open()` opens the first media stream availble to read.
However, the operation mode can be specified via the :code:`mode` second argument.
The above example, opens :code:`mytestvideo.mp4` file in :code:`'rv'` or "read 
video" mode and :code:`myoutput.avi` in :code:`'wv'` or "write video" mode. The 
file reader object :code:`f` is equipped with :code:`read()` method while the 
write object comes with :code:`write()` method. The reader, in addition, has
:code:`readiter()` generator to iterate as long as there are data to read. For more, 
see :py:func:`ffmpegio.open`.

Specify Read Time Range
-----------------------

For both block and stream read operations, you can specify the time range to read 
data from. There are four options available:

.. table:: Read Timing Options
  :class: tight-table

  ========  =======================================================================
  Name      Description
  ========  =======================================================================
  start     Start time. Defaults to the beginning of the stream.
  end       End time. Defaults to the end of the stream.
  duration  Duration in seconds. Defaults to the duration from :code:`start` to the 
            end of the input stream.
  units     Time units. One of ``seconds``, ``frames``, or ``samples``. Defaults 
            to ``seconds``.
  ========  =======================================================================

One of :code:`start`, :code:`end`, :code:`duration` or a combination of two of them
defines the read range:

.. code-block:: python

  >>> url = 'myvideo.mp4'
  >>> info = ffmpegio.probe.video_streams_basic(url)[0]

  >>> #read only the first 1 seconds
  >>> fs, F = ffmpegio.video.read(url, duration=1.0)

  >>> #read the last 2.5 seconds
  >>> fs, F = ffmpegio.video.read(url, end=info['duration'], duration=2.5)

  >>> #read from 1.2 second mark to 2.5 second mark
  >>> fs, F = ffmpegio.video.read(url, start=1.2, end=2.5)
    
.. note::
  If all 3 are given, the read functions honor :code:`start` and :code:`duration` 
  and ignore :code:`end`.

Rather than specifying the times and durations in seconds, :code:`units` option 
allows to specify by the frame numbers for video and sample numbers for audio.
For example::

.. code-block:: python

  >>> #read 30 frame from the 11th frame (remember Python uses 0-based index)
  >>> with ffmpegio.open('myvideo.mp4', start=10, duration=30, units='frames') as f:
  >>>     frame = f.read()
  >>>     # do your thing with the frame data

In this example, the video stream of :code:`'myvideo.mp4'` is first probed for its
frame rate, then the :code:`start` and :code:`duration` arguments are converted to
seconds per the discovered frame rate.

Likewise, the timing of the audio input stream can be set with its sample number::

.. code-block:: python

  >>> #read first 10000 audio samples
  >>> fs, x = ffmpegio.audio.read('myaudio.wav', duration=10000, units='samples')

Now, you may ask about the accuracy of the timing, and this is a very important point
when using FFmpeg in general. FFmpeg is a media playback/recording/transcoding
tool and not a precision data analysis software. As such, it does not and cannot 
guarantee the time accuracy. To quote from its documentation,
        
  "Note that in most formats it is not possible to seek exactly, so ffmpeg will 
  seek to the closest seek point before position. When transcoding and ``-accurate_seek``
  is enabled (the default), this extra segment between the seek point and position 
  will be decoded and discarded."

This being said, video frames are generally seeked correctly with ``-accurate_seek``.
However, the audio stream timing gets a bit dicier due to its frames containing multiple
samples. To overcome this :py:mod:`ffmpegio` always reads the audio stream from the
beginning and truncate unrequested samples. So, it is advised to use the stream read
if multiple audio segments are needed to reduce this necessary overhead.

Specify Data Formats
--------------------

FFmpeg can convert the formats of video pixels and sound samples on the fly. 
This feature is enabled in :py:mod:`ffmpegio` via options :code:`pix_fmt` for
video and :code:`sample_fmt` for audio:

  .. table:: Video :code:`pix_fmt` Option Values
    :class: tight-table

    ===============  ========================================
    :code:`pix_fmt`  Description                
    ===============  ========================================
     :code:`gray`    grayscale                       
     :code:`ya8`     grayscale with transparent alpha channel
     :code:`rgb24`   RGB
     :code:`rgba`    RGB with alpha transparent alpha channel
    ===============  ========================================

  .. table:: Audio :code:`sample_fmt` Option Values
    :class: tight-table

    ==================  ===============================  ===========  ==========
    :code:`sample_fmt`  Description                      min          max
    ==================  ===============================  ===========  ==========
     :code:`u8`         unsigned 8-bit integer           0            255
     :code:`s16`        signed 16-bit integer            -32768       32767
     :code:`s32`        signed 32-bit integer            -2147483648  2147483647
     :code:`flt`        single-precision floating point  -1.0         1.0
     :code:`dbl`        double-precision floating point  -1.0         1.0
    ==================  ===============================  ===========  ==========

.. highlight:: python

For example,

.. code-block:: python

  >>> # auto-convert video frames to grayscale
  >>> fs, RGB = ffmpegio.video.read('myvideo.mp4', duration=1.0) # natively rgb24
  >>> _, GRAY = ffmpegio.video.read('myvideo.mp4', duration=1.0, pix_fmt='gray') 
  >>> RGB.shape
  (29, 640, 480, 3)
  >>> GRAY.shape
  (29, 640, 480, 1)
  
  # auto-convert PNG image to remove transparency with white background
  >>> RGBA = ffmpegio.image.read('myimage.png') # natively rgba with transparency
  >>> RGB = ffmpegio.image.read('myimage.png', pix_fmt='rgb', fill_color='white') 
  >>> RGB.shape
  (100, 396, 4)
  >>> GRAY.shape
  (29, 640, 480, 1)
  
  >>> # auto-convert to audio samples to double precision
  >>> fs, x = ffmpegio.audio.read('myaudio.wav') # natively s16
  >>> _, y = ffmpegio.audio.read('myaudio.wav', sample_fmt='dbl') 
  >>> x.max()
  2324
  >>> y.max()
  0.0709228515625

Note when converting from an image with alpha channel (FFmpeg does not support 
alpha channel in video) the background color may be specified with :code:`fill_color`
option (default: ``'white'``). See `the FFmpeg color specification <https://ffmpeg.org/ffmpeg-utils.html#Color>`__
for the list of predefined color names.