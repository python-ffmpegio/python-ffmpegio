.. highlight:: python
.. _options:

FFmpeg Option References
========================

All open/read/write/filter functions in :py:mod:`ffmpegio` accepts any 
`FFmpeg options <https://ffmpeg.org/ffmpeg.html#Options>`__ as their keyword arguments. Two rules 
apply to construct Python function argument: 

(1) Drop the ``-`` from FFmpeg option name, e.g., enter ``-ss 50`` as ``(..., ss=50, ...)``; and 
(2) All the options are assumed output options by default. To specify input options, append ``_in`` 
    to the option name. To apply ``-ss 50`` to input url, enter ``(..., ss_in=50, ...)``. Global 
    options are automatically identified.

The option values can be specified in any data type, but it must have a ``__str__`` function defined 
to convert Python data to correct FFmpeg string expression.

Common FFmpeg Options
---------------------

==========  =========  =  =  =  =  ============================================================
Name        type       V  A  I  O  Description
==========  =========  =  =  =  =  ============================================================
ss          float      X  X  X  X  Start time in seconds
t           float      X  X  X  X  Duration in seconds 
to          float      X  X  X  X  End time in seconds (ignored if both `ss`` and `t` are set)
r           numeric    X     X  X  Video frame rate in frames/second
ar          numeric       X  X  X  Audio sampling rate in samples/second
s           (int,int)  X     X  X  Video frame size (width, height). Alt. str expression: `wxh`
pix_fmt     str        X     X  X  Video frame pixel format, defaults to auto-detect
vf          str           X     X  Video filtergraph (leave output pad unlabeled)
ac          int           X  X  X  Number of audio channels, defaults to auto-detect
sample_fmt  int           X  X  X  Audio sample format, defaults to None (same as input)
af          str        X        X  Audio filtergraph (leave output pad unlabeled)
crf         int        X        X  H.264 video encoding constant quality factor (0-51)
==========  =========  =  =  =  =  ============================================================

`s` output option
^^^^^^^^^^^^^^^^^

FFmpeg's :code:`-s` output option sets the output video frame size by using the scale video filter. However,
it does not allow non-positive values for width and height which the scale filter accepts. 
:py:mod:`ffmpegio` alters this behavior by checking the :code:`s` argument for <=0 width or height 
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

`map` output options
^^^^^^^^^^^^^^^^^^^^

The output option `-map` is the (only?) FFmpeg option, which could be specified multiple times
in command line input. This goes against :py:mod:`ffmpegio`'s FFmpeg dict structure, and so `map`
argument is handled differently from the others. First, `map` argument must be a non-`str` sequence,
and each of its element is converted to `-map` option. Furthermore, each element could be a str or
else a sequence which items are then stringified and joined together with `':'`.


Video Pixel Formats :code:`pix_fmt`
-----------------------------------

There are many video pixel formats that FFmpeg support, which you can obtain with 
:py:func:`caps.pix_fmts()` function. For the I/O purpose, :py:mod:`ffmpegio` video/image
functions operate strictly with RGB or grayscale formats listed below.

=====  =====  =========  ===================================
ncomp  dtype  pix_fmt    Description
=====  =====  =========  ===================================
  1     \|u8   gray       grayscale
  1     <u2   gray10le   10-bit grayscale
  1     <u2   gray12le   12-bit grayscale
  1     <u2   gray14le   14-bit grayscale
  1     <u2   gray16le   16-bit grayscale (default for <u2)
  1     <f4   grayf32le  floating-point grayscale
  2     \|u1   ya8        grayscale with alpha channel
  2     <u2   ya16le     16-bit grayscale with alpha channel
  3     \|u1   rgb24      RGB
  3     <u2   rgb48le    16-bit RGB
  4     \|u1   rgba       RGB with alpha transparency channel
  4     <u2   rgba64le   16-bit RGB with alpha channel
=====  =====  =========  ===================================

Note that each video pixel format has a specific `dtype` (or `input_dtype`) str argument, which 
follows the NumPy array data type convention.

Audio Sample Formats :code:`sample_fmt`
---------------------------------------

FFmpeg offers its audio channels in both interleaved and planar sample formats (`sample_fmt`, 
run :py:func:`caps.sample_fmts()` to list available formats). For the I/O purpose, 
:py:mod:`ffmpegio` audio functions always use the interleaved formats:

======  ==========
dtype   sample_fmt
======  ==========
  \|u1     u8
  <i2     s16
  <i4     s32
  <f4     flt
  <f8     dbl
======  ==========

Like `pix_fmt`, `sample_fmt` also has concrete relationship to the `dtype` option

Built-in Video Manipulation Options
-----------------------------------

.. deprecated:: 0.12

   This feature has been deprecated. It is now implemented in 
   :py:mod:`filtergraph.presets` to generate a filtergraph, which can then be
   used with :code:`vf` or :code:`filter_complex` options. 

   - :py:func:`filtergraph.presets.filter_video_basic` - a filterchain 
     with scale, crop, flip, and transpose filters
   - :py:func:`filtergraph.presets.remove_alpha` - a filterchain to remove alpha
     channel
   - :py:func:`filtergraph.presets.square_pixels` - a filterchain to square
     pixels
