References: Standard Keyword Options
====================================

| PyPi: `<https://pypi.org/project/ffmpegio/>`__
| GitHub: `<https://github.com/tikuma-lsuhsc/python-ffmpegio>`__

.. warning::
   This package is still in an early alpha stage and under heavy consturction.

All read/write `ffmpegio` functions support a set of default keyword options.

Keyword Options
---------------

=================  =======  =  =  =  =  ===========================================================
Name               type     V  A  R  W  Description
=================  =======  =  =  =  =  ===========================================================
start              float    X  X  X     Start time in seconds or in the units as specified by 
                   int                  `units` parameter. Defaults to the beginning of the stream
end                float    X  X  X     End time in seconds or in the units as specified by `units`
                   int                  parameter. Defaults to the end of the stream
duration           float    X  X  X     Duration in seconds or in the units as specified by `units`
                                        parameter. Defaults to the duration from `start` to the end
                                        of the input stream
units              str      X  X  X     Units of `start`, `end`, and `duration` parameters: 
                                        ``seconds``, ``frames``, or ``samples``. defaults to ``seconds``.
                                        See resolution policy below.
input_frame_rate   numeric  X     X     Input video frame rate in frames/second, overriding the specified 
                                        in the file.  
input_sample_rate  numeric     X  X     Input audio sampling rate in samples/second, overriding the specified 
                                        in the file.
codec              str      X  X     X  Codec, "none", or "copy", defaults to auto-detect from file extension
crf                int      X        X  Video encoding constant quality
frame_rate         numeric  X  X  X  X  Video frame rate in frames/second.
pix_fmt            str      X     X  X  Video frame pixel format, defaults to auto-detect. Run `caps.pixfmts()` to list all available pixel formats.
channels           int         X  X  X  Number of audio channels, defaults to auto-detect
sample_fmt         int         X  X  X  Audio sample format, defaults to None (same as input). Run `caps.samplefmts()` to list available formats and their bits/sample.
force              bool     X  X     X  True to overwrite if file exists or False to skip. If unspecified, FFmpeg will prompt.
=================  =======  =  =  =  =  ===========================================================

Option names may differ in the functions which accepts both video and audio streams, e.g., `ffmpegio.transcode`

Resolution `start` vs. `end` vs. `duration`
-------------------------------------------

Only 2 out of 3 are honored.

+-------+-----+----------+----------------------------------------------------------------------+
|`start`|`end`+`duration`| FFmpeg config                                                        |
+=======+=====+==========+======================================================================+
|   X   |     |          |    start time specified, continue till the end of input              |
+-------+-----+----------+----------------------------------------------------------------------+
|       |   X |          |   start from the beginning of the input till `end` time is hit       |
+-------+-----+----------+----------------------------------------------------------------------+
|       |     |      X   | start from the beginning of the input till encoded `duration` long   |
+-------+-----+----------+----------------------------------------------------------------------+
|  X    |   X |          |   start and end time specified                                       | 
+-------+-----+----------+----------------------------------------------------------------------+
|  X    |     |      X   |   start and duration specified                                       |
+-------+-----+----------+----------------------------------------------------------------------+
|       |   X |      X   |   end and duration specified (actually sets start time)              |
+-------+-----+----------+----------------------------------------------------------------------+
|  X    |   X |      X   |   `end` parameter ignored                                            |
+-------+-----+----------+----------------------------------------------------------------------+

Video formats
-------------

The Numpy array dimensions and dtypes are dictated by the video pixel 
formats:

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

Audio formats
-------------

FFmpeg sample_fmt type and Numpy array dtypes are related as follows

==============  ==========
`numpy.dtype`   sample_fmt
==============  ==========
`numpy.uint8`     u8      
`numpy.int16`     s16     
`numpy.int32`     s32     
`numpy.single`    flt     
`numpy.double`    dbl     
==============  ==========

TODO: support for planar format, i.e., auto-transposing data
