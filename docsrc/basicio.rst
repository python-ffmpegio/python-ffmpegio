.. py:currentmodule:: ffmpegio
.. highlight:: python

.. _basicio:

Basic I/O Functions (:code:`ffmpegio.video`, :code:`ffmpegio.audio`, :code:`ffmpegio.image`, :code:`ffmpegio.media`, :code:`ffmpegio.transcode()`)
==================================================================================================================================================

Overview
--------

.. autosummary::
   :nosignatures:
   :recursive:

   transcode
   video.create
   video.read
   video.write
   video.filter
   image.create
   image.read
   image.filter
   image.write
   audio.create
   audio.read
   audio.write
   audio.filter
   media.read
   media.write
   media.filter

As a command-line tool, one of FFmpeg's most common use cases is to convert a media file/stream from 
one format to another. :py:func:`ffmpegio.transcode()` is a Python function implementing this general usage.
Here is a command-line example to convert MOV file to MP4 file::

   ffmpeg -i input.mov -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k output.mp4

In Python, we can perform the same transcoding by

.. code-block:: python

   output_options = {"c:v": "libx264", "crf": 23, "preset": "medium", 
                     "c:a": "aac", "b:a": "128k"}
   ffmpegio.transcode('input.mov', 'output.mp4', **output_options)
   
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
:code:`s`           :py:type:`tuple[int,int]`                                    X     X  X  Video frame size (width, height). Alt. str expression: :code:`wxh`
:code:`pix_fmt`     :py:class:`str`                                              X     X  X  Video frame pixel format, defaults to auto-detect
:code:`vf`          :py:class:`str`                                                 X     X  Video filtergraph (leave output pad unlabeled)
:code:`ac`          :py:class:`int`                                                 X  X  X  Number of audio channels, defaults to auto-detect
:code:`sample_fmt`  :py:class:`int`                                                 X  X  X  Audio sample format, defaults to :code:`None`  (same as input)
:code:`af`          :py:class:`str`                                              X        X  Audio filtergraph (leave output pad unlabeled)
:code:`crf`         :py:class:`int`                                              X        X  H.264 video encoding constant quality factor (0-51)
==================  ===========================================================  =  =  =  =  =======================================================================

:code:`s` output option
"""""""""""""""""""""""

FFmpeg's :code:`-s` output option sets the output video frame size by using the scale video filter. However,
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
in command line input. This goes against :code:`ffmpegio`'s FFmpeg dict structure, and so :code:`map`
argument is handled differently from the others. First, :code:`map` argument must be a non-`str` sequence,
and each of its element is converted to :code:`-map` option. Furthermore, each element could be a str or
else a sequence which items are then stringified and joined together with :code:`':'`.


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
