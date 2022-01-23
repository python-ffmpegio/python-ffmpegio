.. highlight:: python
.. _options:

FFmpeg Option References
========================

All open/read/write/filter functions in :py:mod:`ffmpegio` accepts any `FFmpeg options <https://ffmpeg.org/ffmpeg.html#Options>`__ as their keyword arguments. Two rules apply to construct Python function argument: 

(1) Drop the `-` from FFmpeg option name, e.g., enter `-ss 50` as `(..., ss=50, ...)`; and 
(2) All the options are by default assumed output options. To specify input options, append `_in` to the option name. To apply `-ss 50` to input url, enter `(..., ss_in=50, ...)`. Global options are automatically identified.

The option values can be specified in any data type, but it must have a `__str__` function defined to convert Python data to correct FFmpeg string expression.

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

Special handling of `s` output option
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Video Pixel Formats :code:`pix_fmt`
-----------------------------------

There are many video pixel formats that FFmpeg support, which you can obtain with 
:py:func:`caps.pix_fmts()` function. For the I/O purpose, :py:mod:`ffmpegio` video/image
functions operate strictly with RGB or grayscale formats listed below.

=====  ==============  =========  ===================================
ncomp  `numpy.dtype`   pix_fmt    Description
=====  ==============  =========  ===================================
  1    `numpy.uint8`   gray       grayscale
  1    `numpy.uint16`  gray16le   16-bit grayscale
  1    `numpy.single`  grayf32le  floating-point grayscale
  2    `numpy.uint8`   ya8        grayscale with alpha channel
  2    `numpy.uint16`  ya16le     16-bit grayscale with alpha channel
  3    `numpy.uint8`   rgb24      RGB
  3    `numpy.uint16`  rgb48le    16-bit RGB
  4    `numpy.uint8`   rgba       RGB with alpha transparency channel
  4    `numpy.uint16`  rgba64le   16-bit RGB with alpha channel
=====  ==============  =========  ===================================

This table defines how the Numpy array dimensions and dtypes are related to
the video pixel formats.


Audio Sample Formats :code:`sample_fmt`
---------------------------------------

FFmpeg offers its audio channels in both interleaved and planar sample formats (`sample_fmt`, 
run :py:func:`caps.sample_fmts()` to list available formats). For the I/O purpose, 
:py:mod:`ffmpegio` audio functions always use the interleaved formats:

==============  ==========
`numpy.dtype`   sample_fmt
==============  ==========
`numpy.uint8`     u8      
`numpy.int16`     s16     
`numpy.int32`     s32     
`numpy.single`    flt     
`numpy.double`    dbl     
==============  ==========

Built-in Video Manipulation Options
-----------------------------------

FFmpeg can manipulate both video and audio streams by filtergraph 
(`FFmpeg Documentation <https://ffmpeg.org/ffmpeg-filters.html#Description>`__).
Video/image routines of :py:mod:`ffmpegio` adds addtional video options to
perform simple video maninpulations without the need of setting up a filtergraph.


.. list-table:: Options to manipulate video frames
  :widths: auto
  :header-rows: 1
  :class: tight-table

  * - name
    - value
    - FFmpeg filter
    - Description
  * - :code:`crop`
    - seq(int[, int[, int[, int]]])
    - `crop <https://ffmpeg.org/ffmpeg-filters.html#crop>`__
    - video frame cropping/padding, values representing the number of pixels to crop from [left top right bottom].
      If positive, the video frame is cropped from the respective edge. If negative, the video frame is padded on 
      the respective edge. If right or bottom is missing, uses the same value as left or top, respectively. If top
      is missing, it defaults to 0.
  * - :code:`flip`
    - {:code:`'horizontal'`, :code:`'vertical'`, :code:`'both'`}
    - `hflip <https://ffmpeg.org/ffmpeg-filters.html#hflip>`__ or `vflip <https://ffmpeg.org/ffmpeg-filters.html#vflip>`__
    - flip the video frames horizontally, vertically, or both.
  * - :code:`transpose`
    - int
    - `transpose <https://ffmpeg.org/ffmpeg-filters.html#transpose-1>`__
    - tarnspose the video frames. Its value specifies the mode of operation. Use 0 for the conventional transpose operation.
      For the others, see the FFmpeg documentation.
  * - :code:`fill_color`
    - str
    - n/a
    - This option is used to auto-convert transparent images to an 
      opaque :code:`pix_fmt`. Its option value specifies a color according to
      `FFmpeg Color Specifications <https://ffmpeg.org/ffmpeg-utils.html#Color>`__.

Note that the these operations are pre-wired to perform in a specific order:

.. blockdiag::
  :caption: Video Manipulation Order

  blockdiag {
    crop -> flip -> transpose;
  }

Be aware of this ordering as these filters are non-commutative (i.e., a change in the 
order of operation alters the outcome). If your desired order of filters differs or
need to use additional filters, use the :code:`vf` option to specify your own filtergraph. 

.. list-table:: Examples of manipulated images
  :class: tight-table

  * - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png')
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM)
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png')

  * - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png', crop=(100,100,0,0), transpose=0)
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM)
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png', crop=(100,100,0,0), transpose=0)

  * - .. plot:: 
    
        IM = ffmpegio.image.read('ffmpeg-logo.png', crop=(100,100,0,0), flip='both', s=(200,50))
        plt.figure(figsize=(IM.shape[1]/96, IM.shape[0]/96), dpi=96)
        plt.imshow(IM)
        plt.gca().set_position((0, 0, 1, 1))
        plt.axis('off')
    
      .. code-block:: python

        ffmpegio.image.read('ffmpeg-logo.png', crop=(100,100,0,0), flip='both', size=(200,-1))
