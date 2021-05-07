.. _adv_ffmpeg:

:py:mod:`ffmpegio.ffmpeg`: Direct invocation of FFmpeg subprocess
=================================================================

Instead of indirectly calling FFmpeg via :ref:`Basic I/O Functions <basicio>` or FFprobe via
:ref:`Media Probe Functions <probe>`, you can directly invoke a FFmpeg subprocess using 
the functions in :py:mod:`ffmpegio.ffmpeg` module.

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.ffmpeg.ffprobe
   ffmpegio.ffmpeg.run
   ffmpegio.ffmpeg.run_sync
   ffmpegio.ffmpeg.parse
   ffmpegio.ffmpeg.compose

While both :py:func:`ffmpegio.ffmpeg.run` and :py:func:`ffmpegio.ffmpeg.run_sync` supports
the :code:`args` argument of Python's :py:func:`subprocess.run` and :py:class:`subprocess.Popen` 
constructor, the FFmpeg command argument can also be specified with a Python dict: 
see :ref:`its specification page <adv_args>` for the details.

:py:mod:`ffmpegio.ffmpeg` Module Reference
------------------------------------------

.. autofunction:: ffmpegio.ffmpeg.ffprobe
.. autofunction:: ffmpegio.ffmpeg.run
.. autofunction:: ffmpegio.ffmpeg.run_sync
.. autofunction:: ffmpegio.ffmpeg.parse
.. autofunction:: ffmpegio.ffmpeg.compose
