.. highlight:: python
.. _quick:

Quick Start Guide
=================

Install
-------

To use :py:mod:`ffmpegio`, the package must be installed on Python as well as  
having the FFmpeg binary files at a location :py:mod:`ffmpegio` can find.

Install the full :py:mod:`ffmpegio` package via ``pip``:

.. code-block:: bash

   pip install ffmpegio

If `numpy.ndarray` data I/O is not needed, instead use 

.. code-block:: bash

   pip install ffmpegio-core


If FFmpeg is not installed on your system, please follow the instructions on
:ref:`Installation page <install>`

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
:code:`ffmpegio`'s :ref:`ffmpegio:probe<probe>` module wraps ffprobe with 5
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
    >>> pprint(vst_info) 
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
    >>> pprint(ast_info) 
    [{'channel_layout': 'stereo',
    'channels': 2,
    'codec_name': 'mp2',
    'duration': 66.40325555555556,
    'index': 0,
    'nb_samples': 2928384,
    'sample_fmt': 'fltp',
    'sample_rate': 44100,
    'start_time': 0.0}]

To obtain the complete ffprobe output, use :py:func:`ffmpegio.probe.full_details`,
and to obtain specific format or stream fields, use :py:func:`ffmpegio.probe.query`. 
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

  >>> with ffmpegio.open('mytestvideo.mp4', 'rv', blocksize=100) as f,
  >>>      ffmpegio.open('myoutput.avi', 'wv', f.frame_rate) as g:
  >>>         for frames in f: # iterates over all frames, 100 frames at a time
  >>>             output = my_processor(frames) # function to process data
  >>>             g.write(output) # send the processed frames to 'myoutput.avi' 

By default, :code:`ffmpegio.open()` opens the first media stream available to read.
However, the operation mode can be specified via the :code:`mode` second argument.
The above example, opens :code:`mytestvideo.mp4` file in :code:`'rv'` or "read 
video" mode and :code:`myoutput.avi` in :code:`'wv'` or "write video" mode. The 
file reader object :code:`f` is an Iterable object, which returns the next set of
frames (the number set by the :code:`blocksize` argument). For more, 
see :py:func:`ffmpegio.open`.

Specify Read Time Range
-----------------------

For both block and stream read operations, you can specify the time range to read 
data from. There are four options available:

.. table:: Read Timing Options
  :class: tight-table

  =============  ========================================================================
  Name           Description
  =============  ========================================================================
  :code:`ss`     Start time in seconds
  :code:`t`      Duration in seconds
  :code:`to`     End time in seconds (ignored if :code:`t_in` is also specified)
  =============  ========================================================================

Note it is also possible to specify these timing options for the input (i.e., using the 
options :code:`ss_in`, :code:`t_in`, and :code:`to_in`). The input options, especially 
:code:`ss_in`, may run faster but potentially less accurate. See `FFmpeg documentation 
<https://ffmpeg.org/ffmpeg.html#Options>`__ for the explanation.

.. code-block:: python

  >>> url = 'myvideo.mp4'

  >>> #read only the first 1 seconds
  >>> fs, F = ffmpegio.video.read(url, t=1.0)

  >>> #read from 1.2 second mark to 2.5 second mark
  >>> fs, F = ffmpegio.video.read(url, t=1.2, to=2.5)
    
To specify by the frame numbers for video and sample numbers for audio, user must
convert the units to seconds using :py:func:`probe`. For example:

.. code-block:: python

  >>> # get frame rate of the (first) video stream
  >>> info = ffmpegio.probe.video_streams_basic('myvideo.mp4')
  >>> fs = info[0]['frame_rate'] 

  >>> #read 30 frame from the 11th frame (remember Python uses 0-based index)
  >>> with ffmpegio.open('myvideo.mp4', t=10/fs, t=30/fs) as f:
  >>>     frame = f.read()
  >>>     # do your thing with the frame data

Likewise, for an audio input stream:

.. code-block:: python

  >>> # get sampling rate of the (first) audio stream
  >>> info = ffmpegio.probe.audio_streams_basic('myaudio.wav')
  >>> fs = info[0]['sample_rate'] 

  >>> #read first 10000 audio samples
  >>> fs, x = ffmpegio.audio.read('myaudio.wav', t=10000/fs)

Specify Output Frame/Sample Size
--------------------------------

FFmpeg let you change video size or the number of audio channels via output 
options :code:`s` and :code:`ac`, respectively, without setting up a 
filtergraph. For example,

.. code-block:: python

  >>> # auto-scale video frame
  >>> fs, F = ffmpegio.video.read('myvideo.mp4', t=1.0) # natively 320x240
  >>> F.shape
  (30, 240, 320, 3)

  >>> # halve the size
  >>> width = 160
  >>> height = 120  
  >>> _, G = ffmpegio.video.read('myvideo.mp4', t=1.0, s=(width,height)) 
  >>> G.shape
  (29, 120, 160, 3)
  
  >>> # auto-convert to mono
  >>> fs, x = ffmpegio.audio.read('myaudio.wav') # natively stereo
  >>> _, y = ffmpegio.audio.read('myaudio.wav', ac=1) # to mono
  >>> x.shape
  (44100, 2)
  >>> y.shape
  (44100, 1)

To customize the conversion configuration, use :code:`vf` output option 
with with :code:`scale` filter or :code:`af` output option with 
:code:`channelmap` or :code:`pan` or other channel mixing filter

Specify Sample Formats
----------------------

FFmpeg can also convert the formats of video pixels and sound samples on the fly. 
This feature is enabled in :py:mod:`ffmpegio` via output options :code:`pix_fmt` 
for video and :code:`sample_fmt` for audio. 

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
  >>> fs, RGB = ffmpegio.video.read('myvideo.mp4', t=1.0) # natively rgb24
  >>> _, GRAY = ffmpegio.video.read('myvideo.mp4', t=1.0, pix_fmt='gray') 
  >>> RGB.shape
  (29, 640, 480, 3)
  >>> GRAY.shape
  (29, 640, 480, 1)
  
  >>> # auto-convert PNG image to remove transparency with white background
  >>> RGBA = ffmpegio.image.read('myimage.png') # natively rgba with transparency
  .. >>> RGB = ffmpegio.image.read('myimage.png', pix_fmt='rgb24', fill_color='white') 
  >>> RGB.shape
  (100, 396, 4)
  >>> RGB.shape
  (100, 396, 3)
  
  >>> # auto-convert to audio samples to double precision
  >>> fs, x = ffmpegio.audio.read('myaudio.wav') # natively s16
  >>> _, y = ffmpegio.audio.read('myaudio.wav', sample_fmt='dbl') 
  >>> x.max()
  2324
  >>> y.max()
  0.0709228515625

Note when converting from an image with alpha channel (FFmpeg does not support 
alpha channel in video input) the background color may be specified with 
:code:`fill_color` option (which defaults to ``'white'``). 
See `the FFmpeg color specification <https://ffmpeg.org/ffmpeg-utils.html#Color>`__
for the list of predefined color names.


.. list-table:: Examples of changing image format
  :class: tight-table

  * - :code:`'rgba'` (original)
    - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png')
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM)
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png')

  * - :code:`'rgb24'` with 'Linen' background
    - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png')
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM)
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png', pix_fmt='rgb24', fill_color='linen')

  * - :code:`'ya8'`
    - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png', pix_fmt='ya8')
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM[...,0], alpha=IM[...,1]/255, cmap='gray')
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png', pix_fmt='ya8')

  * - :code:`'gray'` with light gray background
    - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png', pix_fmt='gray', fill_color='#F0F0F0')
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM, cmap='gray')
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png', pix_fmt='gray', 
            fill_color='#F0F0F0')

Progress Callback
-----------------

FFmpeg has :code:`-progress` option, which sends program-friendly progress
information to url. :py:mod:`ffmpegio` takes advantage of this option to
let user monitor the transcoding progress with a callback, which could be 
set with :code:`progress` argument of all media operations. The callback
function must have the following signature:

.. code-block:: python

  progress_callback(status:dict, done:bool) -> None|bool

The :code:`status` dict containing the information similar to what FFmpeg 
displays on console. The second argument :code:`done` is only :code:`True` 
on the last progress call. Here is an example of :code:`status` dict:

.. code-block:: python

  {'bitrate': '61.9kbits/s',
  'drop_frames': 0,
  'dup_frames': 0,
  'fps': 336.18,
  'frame': 1014,
  'out_time': '00:00:33.877914',
  'out_time_ms': 33877914,
  'out_time_us': 33877914,
  'speed': '11.2x',
  'stream_0_0_q': 29.0,
  'total_size': 262192}  

While FFmpeg does not report percent progress, it is possible to compute it from
:code:`frame` or :code:`out_time` if you know the total number of output frames
or the output duration, respectively.

If an FFmpeg media stream object is invoked by :py:func:`ffmpegio.open` 
with :code:`progress` callback argument, the callback function can terminate
the FFmpeg execution by returning :code:`True`. This feature is useful for GUI
programming.
