.. _adv_ffmpeg:

:py:mod:`ffmpegio.ffmpegprocess`: Direct invocation of FFmpeg subprocess
========================================================================

Instead of indirectly calling FFmpeg with :py:mod:`ffmpegio`'s :ref:`Basic I/O Functions <basicio>`, 
you can directly invoke a FFmpeg subprocess with :py:mod:`ffmpegio.ffmpegprocess` module, 
which mocks Python's builtin :py:mod:`subprocess` module.

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.ffmpegprocess.run
   ffmpegio.ffmpegprocess.Popen

While both :py:func:`ffmpegio.ffmpegprocess.run` and :py:class:`ffmpegio.ffmpegprocess.Popen` 
constructor accepts the :code:`args` argument of Python's :py:func:`subprocess.run` and 
:py:class:`subprocess.Popen` constructor, the FFmpeg command argument can also be specified 
with a Python dict: 
see :ref:`its specification page <adv_args>` for the details.

:py:mod:`ffmpegio.ffmpeg` Module Reference
------------------------------------------

.. autofunction:: ffmpegio.ffmpegprocess.run
.. autoclass:: ffmpegio.ffmpegprocess.Popen
   :members:
