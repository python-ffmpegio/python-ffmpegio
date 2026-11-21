.. py:currentmodule:: ffmpegio
.. highlight:: python

.. _basicio:

Basic I/O (:code:`ffmpegio.video`, :code:`ffmpegio.audio`, :code:`ffmpegio.image`, :code:`ffmpegio.media`, :code:`ffmpegio.transcode()`)
========================================================================================================================================

Overview
--------

As a command-line tool, one of FFmpeg"s most common use cases is to convert a media file/stream from 
one format to another. :py:func:`ffmpegio.transcode()` is the Python function implementing this general usage.
Here is a command-line example to convert MOV file to MP4 file::

   ffmpeg -i input.mov -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k output.mp4

In Python, we can perform the same transcoding by

.. code-block:: python

   output_options = {"c:v": "libx264", "crf": 23, "preset": "medium", 
                     "c:a": "aac", "b:a": "128k"}
   ffmpegio.transcode("input.mov", "output.mp4", **output_options)
   
The output option keyword arguments had to expanded from a :py:class:`dict` because of the option 
names with stream specifiers, e.g., :code:`-c:v` and :code:`-c:a`.

The primary purpose of :py:mod:`ffmpegio` is to provide Python interface to read/write raw media data,
and it has a specialized submodule for each media type (:code:`ffmpegio.video`, :code:`ffmpegio.audio`, 
:code:`ffmpegio.image`, and :code:`ffmpegio.media`). The last one, :code:`ffmpegio.media`, is a multi-
stream mixed-media handling module. These submodules contain read/write/filter functions.

======================  ==============  ===============  ================  ================
Submodule               :code:`read()`  :code:`write()`  :code:`filter()`  :code:`create()`
======================  ==============  ===============  ================  ================
:code:`ffmpegio.video`        ✅               ✅                ✅               ✅
:code:`ffmpegio.audio`        ✅               ✅                ✅               ✅
:code:`ffmpegio.image`        ✅               ✅                ✅               ✅
:code:`ffmpegio.media`        ✅               ✅                ✅
======================  ==============  ===============  ================  ================

:code:`ffmpegio.media` does not support :code:`create()`, i.e., media data generation function using 
an input FFmpeg filtergraph by design. If such application arises, :py:func:`ffmpegio.media.read()` 
can take a :py:class:`ffmpegio.filtergraph.Graph` object as an input URL.

Single-Stream Readers
---------------------

.. autosummary::
   :nosignatures:

   video.read
   image.read
   audio.read


The :code:`read()` functions take a media URL/file path and obtain raw media data blob of a target stream.
The output data format depends on the plugin configuration, which can be checked with :py:func:`ffmpegio.using()`
and can be changed with :py:func:`ffmpegio.use()`. In this document, we assume that :py:mod:`numpy` is installed
so that both :code:`ffmpegio.using("audio")` and :code:`ffmpegio.using("video")` returns :code:`"read_numpy"`.

Here are basic examples of the single-stream readers:

.. code-block:: python

   import ffmpegio as ff

   fs, audio_data = ff.audio.read("my_audio.mp3", sample_fmt="dbl", ac=1)
   # input keyword arguments:
   #   sample_fmt="dbl" - set samples to be float64 format
   #   ac=1 - if necessary, convert audio channel format to mono to 
   #          guarantee return 1D array
   #
   # outputs:
   #   fs : int - the sampling rate of the audio data in samples/second
   #   audio_data : np.ndarray - a 1D float64 array of all the audio samples

   fps, video_data = ff.video.read("my_video.mp4", to=1, pix_fmt="gray")
   # input keyword arguments:
   #   to=1 : Limits to read only the first second
   #   pix_fmt="gray" : if necessary, convert video pixels to 8-bit grayscale format
   #                    (= 1 color component, 4th dimension is thus dropped)
   #
   # outputs:
   #   fps : Fraction - the frame rate of the video data in frames/second 
   #   video_data : np.ndarray - 3D uint8 array (frames x height x width) 
   #                containing the first one second of frames

   image_data = ff.image.read("my_video.mp4", ss=2.345, s=(480,320))
   # input keyword arguments:
   #   ss=2.345 : capture the nearest frame to 2.345 second mark
   #   s=(480,320) : resize the video frame to 480-pixels wide by 320-pixels high
   #
   # output:
   #   image_data : np.ndarray - 3D uint8 array (320 x 480 x 3) containing the
   #                video frame at 2.345 second timemark. The pixels are in RGB24
   #                format. The 3rd dimension is in the order of Red, Green, and Blue

The FFmpeg options such as :code:`sample_fmt`, :code:`pix_fmt`, :code:`ss`, and :code:`to` plays 
crucial roles to configure these reader functions. See `options`_ for the basic rules and study
`the FFmpeg documentation <https://ffmpeg.org/ffmpeg.html#Options>`__ for all the options.

.. note::

   Use :py:func:`ffmpegio.video.read()` and :py:func:`ffmpegio.media.read()` with caution as 
   the returned raw video data can be extremely large, possibly taking up all the available memory. 
   Use :py:func:`ffmpegio.probe.video_streams_basic()` first to gather the information and restrict 
   the time range with :code:`ss`, :code:`to`, :code:`t`, or :code:`vframes` FFmpeg options. 
   
   For a block-processing application, it"s often better to use :doc:`streamio` and use 
   :py:func:`open()` to create a streaming I/O class.


Alternate input formats
^^^^^^^^^^^^^^^^^^^^^^^

In addition to specify the input URL, these reader functions can take Python"s file-like 
(or IO stream) object as well as a :py:class:`bytes`-like object (i.e., 
:py:class:`memoryview`-able object) containing the entire input file data.

The first audio read example above can be rewritten as follows. First, the file-like 
object as input:

.. code-block:: python

   with open("my_audio.mp3", "rb") as file:
      fs, audio_data = ff.audio.read(file, sample_fmt="dbl", ac=1)

Next, the byte-like object as input:

.. code-block:: python

   with open("my_audio.mp3", "rb") as file:
      mp3data = file.read()

   fs, audio_data = ff.audio.read(mp3data, sample_fmt="dbl", ac=1)

Both of these produces the same output as providing :code:`"my_audio.mp3"` as the input URL.

.. important::

   In general, it"s more performant to let FFmpeg handle the file I/O by giving it the URL/file path.
   Use these alternate input formats only when the source file/stream is not accessible from your
   Python program.

   Also, both of these options rely on using `the pipe protocol <https://ffmpeg.org/ffmpeg-protocols.html#pipe>`__
   to pass the data from Python to FFmpeg. Some media formats (like mp4) may fail because they require the 
   input file to be seekable. Pipes cannot be seeked.

Output shape control
^^^^^^^^^^^^^^^^^^^^

By default, the reader functions set :code:`squeeze=True` so that the output shape does not contain any 
singleton dimensions. If the number of video color components or the number of audio channels is :code:`1` 
(e.g., grayscale video or monaural audio), the last dimension gets dropped. Likewise, if only one video 
frame is present over the specified time interval, the first dimension may be dropped.

Setting :code:`squeeze=False` guarantees that the reader functions returns data arrays of a known dimensionality:
4D for video, 3D for image, and 2D for audio. This is useful when a Python program is subject to opening 
arbitrary media files.

Extra inputs
^^^^^^^^^^^^

It is possible for the reader functions to accept multiple inputs so that FFmpeg combine the streams
to form one output stream. 

For example, :py:func:`ffmpegio.image.read()` can be used to create an image which has
the frames of two videos side by side at the one-second mark by using the :code:`hstack` 
FFmpeg filter:

.. code-block:: python

   image_1vs1 = ffmpegio.image.read(["video1.mp4", "video2.mp4"], ss=1, 
                                    filter_complex="[0][1]hstack")

To show frames at different time, you can specify different :code:`ss` input options to the inputs
instead of a single :code:`ss` output option:

.. code-block:: python

   image_1vs2 = ffmpegio.image.read([("video1.mp4", {"ss": 1}), ("video2.mp4", {"ss": 2})], 
                                    filter_complex="[0][1]hstack")

.. note::

   :py:mod:`ffmpegio` reader functions pre-analyze the filters to identify the stream
   information (name, stream type, data type, and data shape) of complex filtergraph 
   outputs. If the reader is called without the `map` option, it auto-maps the complex 
   filtergraph output stream accordingly.

Extra outputs (experimental)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The reader functions accept the optional :code:`extra_outputs` keyword argument to create a new
media file encoding the raw media data, which is being returned. This is only useful if the input 
stream is a live stream or FFmpeg filters the input stream so that what returned to Python is different 
from the source. The extra output streams must be created explicitly by assigning a complex filtergraph
via the :code:`filter_complex` keyword argument and providing the :code:`map` options to all the output
streams, including the raw output.

For example, FFmpeg resamples the audio first, the resampled audio may be stored in a new file for
later record:

.. code-block:: python

   fs, x = ffmpegio.audio.read("my_audio.mp3", filter_complex="[0]aresample=16000,asplit[out1][out2]",
                               map=["[out1]"], extra_outputs=[("archive_16k.flac", {"map": "[out2]"})])

.. warning::

   This feature is not final and subject to change in future releases.

Single-Stream Writers
---------------------

.. autosummary::
   :nosignatures:

   video.write
   image.write
   audio.write


The :code:`write()` functions take a raw media data blob from Python and create a media file/stream.
Unlike :code:`read()`, :py:mod:`ffmpegio` auto-selects the first writer-helper hook which can handle
the given raw data. 

The audio and video writers requires three arguments: output file name (url), sampling or frame rate,
and the raw data blob. For image writing, only the url and data are needed. :py:mod:`ffmpegio` will 
auto-analyze and configure the FFmpeg input options and FFmpeg will automatically configure the rest. 
User may specify additional options, including FFmpeg to further filter the data.

Here are basic examples of the single-stream writers:

.. code-block:: python

   import ffmpegio as ff

   ff.audio.write("my_audio.mp3", fs, audio_data)

   ff.video.write("my_video.mp4", fps, video_data, c="libx264", crf=23, preset="medium")

   ff.image.write("my_image.png", image_data)

Extra inputs
^^^^^^^^^^^^

Additional input sources (encoded media files/urls) can be supplied to the writers. This would be 
useful to:

- Add an audio track to the video
- Overlay the video onto an existing video

Extra outputs
^^^^^^^^^^^^^

Multiple output urls may be specified by providing a list of outputs.
Each output may be specified by its file name/url only or by a tuple of
the file name/url and a :py:class`dict` of FFmpeg output option values.

For example, to save the data in different formats:

.. code-block:: python

   ff.audio.write(["my_audio.mp3","my_audio.flac"], fs, audio_data)

Or to create video files with different quality settings:

.. code-block:: python

   ff.video.write([("my_video.mp3", {"crf": 13}), ("my_video.mp3", {"crf": 23})], 
                  fps, video_data)


Single-Stream Filters
---------------------

.. autosummary::
   :nosignatures:

   video.filter
   image.filter
   audio.filter


`Filtering <https://ffmpeg.org/ffmpeg-filters.html>`__ is a powerful FFmpeg feature 
to modify/combine/split media streams.
The :code:`filter()` functions are Python interfaces to run FFMpeg filters on 
raw input media data and capture the output raw media data.

.. code-block:: python

   # The first example on the FFmpeg filters documentation 
   expr = "split [main][tmp]; [tmp] crop=iw:ih/2:0:0, vflip [flip]; [main][flip] overlay=0:H/2"
   fps_out, out_video = ff.video.filter(expr, fps_in, in_video)

   # same filter applied on an image (i.e., single frame)
   out_image = ff.image.filter(expr, in_image)

   # audio filter example: resample to 8000 S/s and lowpass filter with 1000 Hz cutoff.
   aexpr = "aresample=8000, lowpass=1000"
   fs_out, out_audio = ff.audio.filter(aexpr, fs_in, in_audio)

Extra inputs and outputs
^^^^^^^^^^^^^^^^^^^^^^^^

The single-stream :code:`filter()` functions accept additional input or output
urls to compliment the primary raw input and output streams.

A simple example is to overlay the Python-generated mask (in a RGBA format)
to the source video (:file:`original.mp4`) and copy the output to 
:file:`archive.mp4` for record.

.. code-block:: python

   expr = "[0:v][1:v] overlay; split[out1][out2]"
   fps_out, out_video = ff.video.filter(expr, fps_in, in_video,
                                        extra_inputs = ["original.mp4"],
                                        extra_outputs = ["archive.mp4"])

Like other functions, these arguments accepts a tuple pair of 
url and its FFmpeg options.

Implicit filtering
^^^^^^^^^^^^^^^^^^

FFmpeg automatically inserts a filter for some output options, e.g., output
rate (:code:`-r` and :code:`-ar`) and format (:code:`-pix_fmt` and 
:code:`sample_fmt`). While there are equivalent filters (e.g., :code:`fps`, 
:code:`format`, :code:`aformat`) it is often more convenient
to use the output options instead of defining a filtergraph. 

Each of the following pairs of explicit and implicit :code:`filter()` function calls 
are equivalent:

.. code-block:: python

   # explicit video filtering
   output_fps, video_output = video.filter("fps=30, format=gray", input_fps)

   # equivalent implicit video filtering
   output_fps, video_output = video.filter(None, input_fps, input, r=30, pix_fmt="gray")

   # explicit audio filtering
   output_fs, audio_output = audio.filter("aformat=dbl:8000:mono", input_fs, input)

   # equivalent implicit audio filtering
   output_fs, audio_output = audio.filter(None, input_fs, input, sample_fmt='dbl', ar=8000, ac=1)

Which FFmpeg option is used?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Under the hood, the :code:`filter()` functions assigns the filtergraph expression to either
the output :code:`-filter` option (equivalently the :code:`-vf` or :code:`-af` option) or the global 
:code:`-filter_complex` option. The :code:`-filter` option is used by default unless :code:`extra_inputs`
or :code:`extra_outputs` arguments are specified.

Single-Stream Creators
----------------------

.. autosummary::
   :nosignatures:

   video.create
   image.create
   audio.create

FFmpeg source filters (`audio <https://ffmpeg.org/ffmpeg-filters.html#Audio-Sources>`__ 
and `video <https://ffmpeg.org/ffmpeg-filters.html#Video-Sources>`__) are filters taking
no input. The :code:`create()` functions accept a filtergraph headed by one of the source
filters to generate media data.

.. code-block:: python

   # Generate ten-second of a sin signal with frequency of 440 Hz, set sample rate to 8000 Hz
   fs, x = audio.create("aevalsrc=sin(440*2*PI*t):s=8000:d=10")

   # Generate an HD video at 10 frames per second with a duration of 5.3 seconds
   fps, frames = video.create("testsrc=duration=5.3:size=hd1080:rate=10")

Other filters may follow these source filters. Only requirement of the source filtergraph is
that it takes zero input and produces one output (of the correct media type). For example, a 
fade-in effect to the audio example above could be added by

.. code-block:: python

   # added 1-second fade in effect
   fs, x = audio.create("aevalsrc=sin(440*2*PI*t):s=8000:d=1, afade=t=in:ss=0:d=1")

Multistream Functions
---------------------

.. autosummary::
   :nosignatures:

   media.read
   media.write
   media.filter

The :code:`fmpegio.media` module extends read/write/filter operations to multiple 
raw streams. The APIs closely follows those of the single-stream functions, but the raw data
format is changed to support multiple raw streams.

First, :py:func:`ffmpegio.media.read()` by default reads all the streams in the input url,
and returns its rates and data outputs as :py:class:`dict`'s keyed by stream specifier :py:class:`str`
with the syntax: :code:`"input_file_id:stream_type:stream_index"`. 

Assuming :file:`my_video.mp4` contains one video and one audio streams, then the returned :code:`r` and :code:`data` of

.. code-block:: python

   r, data = ffmpegio.media.read("my_video.mp4")

are both :py:class:`dict` with the same keys: :code:`"0:v:0"` and :code:`"0:a:0"`. The streams can be explicitly specified:

.. code-block:: python

   r, data = ffmpegio.media.read("my_video.mp4", "0:v:0", "0:a:0")

The stream selection argument can be replaced by an FFmpeg output option :py:class:`dict`. 
This feature could be used to retrieve original and modified version of a media stream.
For example, the following retrieves 

.. code-block:: python

   r, data = ffmpegio.media.read("my_audio.flac", "0:a:0", {'map': '0:a:0', 'ar': 4000})






.. _options:

FFmpeg Options
--------------

All read/write/filter/create functions in :code:`ffmpegio` accepts any 
`FFmpeg options <https://ffmpeg.org/ffmpeg.html#Options>`__ as their keyword arguments. 


Basic Rules
^^^^^^^^^^^

Two rules apply to convert FFMpeg options to a Python function keyword arguments:

(1) Drop the :code:`-` from FFmpeg option name, e.g., enter :code:`-ss 50` as :code:`(..., ss=50, ...)`; and 
(2) All the options are assumed output options by default. To specify input options, append :code:`_in` 
    to the option name. To apply :code:`-ss 50` to input url, enter :code:`(..., ss_in=50, ...)`. Global 
    options are automatically identified.

The option values can be specified in any data type, but it must have a :code:`__str__` function defined 
to convert Python data to correct FFmpeg string expression.

Common FFmpeg Options
^^^^^^^^^^^^^^^^^^^^^

==================  ===========================================================  =  =  =  =  =======================================================================
Name                type                                                         V  A  I  O  Description
==================  ===========================================================  =  =  =  =  =======================================================================
:code:`ss`          :py:class:`float`                                            X  X  X  X  Start time in seconds
:code:`t`           :py:class:`float`                                            X  X  X  X  Duration in seconds 
:code:`to`          :py:class:`float`                                            X  X  X  X  End time in seconds (ignored if both :code:`ss` and :code:`t` are set)
:code:`r`           :py:class:`int` | :py:class:`Fraction <fractions.Fraction>`  X     X  X  Video frame rate in frames/second
:code:`ar`          :py:class:`int`                                                 X  X  X  Audio sampling rate in samples/second
:code:`s`           :code:`tuple[int,int]`                                       X     X  X  Video frame size (width, height). Alt. str expression: :code:`wxh`
:code:`pix_fmt`     :py:class:`str`                                              X     X  X  Video frame pixel format, defaults to auto-detect
:code:`vf`          :py:class:`str`                                                 X     X  Video filtergraph (leave output pad unlabeled)
:code:`ac`          :py:class:`int`                                                 X  X  X  Number of audio channels, defaults to auto-detect
:code:`sample_fmt`  :py:class:`int`                                                 X  X  X  Audio sample format, defaults to :code:`None`  (same as input)
:code:`af`          :py:class:`str`                                              X        X  Audio filtergraph (leave output pad unlabeled)
:code:`crf`         :py:class:`int`                                              X        X  H.264 video encoding constant quality factor (0-51)
==================  ===========================================================  =  =  =  =  =======================================================================

:code:`s` output option
"""""""""""""""""""""""

FFmpeg"s :code:`-s` output option sets the output video frame size by using the scale video filter. However,
it does not allow non-positive values for width and height which the scale filter accepts. 
:code:`ffmpegio` alters this behavior by checking the :code:`s` argument for <=0 width or height 
and convert to :code:`vf` argument.

============  ============================================================
width/height  Description
============  ============================================================
n (n>0)       Specifying the output size to be n pixels
0             Use the input size for the output
-n            Scale the dimension proportional to the other dimension then
              make sure that the calculated dimension is divisible by n 
              and adjust the value if necessary. Only one of width or 
              height can be negative valued.
============  ============================================================

Note that passing both :code:`s` with a non-positive value and :code:`vf` 
will raise an exception.

:code:`map` output options
""""""""""""""""""""""""""

The output option :code:`-map` is the (only?) FFmpeg option, which could be specified multiple times
in command line input. This goes against :code:`ffmpegio`"s FFmpeg dict structure, and so :code:`map`
argument is handled differently from the others. First, :code:`map` argument must be a non-`str` sequence,
and each of its element is converted to :code:`-map` option. Furthermore, each element could be a str or
else a sequence which items are then stringified and joined together with :code:`":"`.


.. _pix_fmt_opts:

Video Pixel Formats (:code:`pix_fmt`)
"""""""""""""""""""""""""""""""""""""

There are many video pixel formats that FFmpeg support, which you can obtain with 
:py:func:`ffmpegio.caps.pix_fmts()` function. For the I/O purpose, :code:`ffmpegio` video/image
functions operate strictly with RGB or grayscale formats listed below.

=====  =====  =========  ===================================
ncomp  dtype  pix_fmt    Description
=====  =====  =========  ===================================
  1     \|u8  gray       grayscale
  1     <u2   gray10le   10-bit grayscale
  1     <u2   gray12le   12-bit grayscale
  1     <u2   gray14le   14-bit grayscale
  1     <u2   gray16le   16-bit grayscale (default for <u2)
  1     <f4   grayf32le  floating-point grayscale
  2     \|u1  ya8        grayscale with alpha channel
  2     <u2   ya16le     16-bit grayscale with alpha channel
  3     \|u1  rgb24      RGB
  3     <u2   rgb48le    16-bit RGB
  4     \|u1  rgba       RGB with alpha transparency channel
  4     <u2   rgba64le   16-bit RGB with alpha channel
=====  =====  =========  ===================================

Note that each video pixel format has a specific :code:`dtype` (or :code:`input_dtype`) str argument, which 
follows the NumPy array data type convention.

Audio Sample Formats :code:`sample_fmt`
"""""""""""""""""""""""""""""""""""""""

FFmpeg offers its audio channels in both interleaved and planar sample formats (:code:`sample_fmt`, 
run :py:func:`ffmpegio.caps.sample_fmts()` to list available formats). For the I/O purpose, 
:code:`ffmpegio` audio functions always use the interleaved formats:

======  ==========
dtype   sample_fmt
======  ==========
  \|u1     u8
  <i2     s16
  <i4     s32
  <f4     flt
  <f8     dbl
======  ==========

Like :code:`pix_fmt`, :code:`sample_fmt` also has concrete relationship to the :code:`dtype` option

API References
--------------

.. autofunction:: ffmpegio::audio.create
.. autofunction:: ffmpegio::audio.filter
.. autofunction:: ffmpegio::audio.read
.. autofunction:: ffmpegio::audio.write
.. autofunction:: ffmpegio::image.create
.. autofunction:: ffmpegio::image.filter
.. autofunction:: ffmpegio::image.read
.. autofunction:: ffmpegio::image.write
.. autofunction:: ffmpegio::media.filter
.. autofunction:: ffmpegio::media.read
.. autofunction:: ffmpegio::media.write
.. autofunction:: transcode
.. autofunction:: ffmpegio::video.create
.. autofunction:: ffmpegio::video.filter
.. autofunction:: ffmpegio::video.read
.. autofunction:: ffmpegio::video.write
