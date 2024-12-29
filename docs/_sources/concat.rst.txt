.. highlight:: python
.. _concat:

`FFConcat` Class: Concatenating Media Files
===========================================

FFmpeg supports different approaches to concatenate media files as described on 
`their Wiki Page <https://trac.ffmpeg.org/wiki/Concatenate>`__. If many files 
are concatenated, any of these approaches results in lengthy command (or a 
ffconcat listing file). The :py:class:`ffmpegio.FFConcat` class primarily focus on
the concat demuxer and abstracts the ffconcat listing file when running `ffmpegio` 
commands.

.. autoclass:: ffmpegio.FFConcat
   :members:
