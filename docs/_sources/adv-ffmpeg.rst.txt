.. highlight:: python
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
   ffmpegio.ffmpegprocess.run_two_pass
   ffmpegio.ffmpegprocess.Popen

While both :py:func:`ffmpegio.ffmpegprocess.run` and :py:class:`ffmpegio.ffmpegprocess.Popen` 
constructor accepts the :code:`args` argument of Python's :py:func:`subprocess.run` and 
:py:class:`subprocess.Popen` constructor, the FFmpeg command argument can also be specified 
with a Python dict: see :ref:`its specification page <adv_args>` for the details.

:py:func:`ffmpegio.ffmpegprocess.run_two_pass` runs FFmpeg twice to perform two-pass video 
encoding. The audio encoding is automatically disabled during the first pass by default. It
also offers a finer control of which options to turn on/off during the first pass.

:py:mod:`ffmpegio.ffmpegprocess` Module Reference
-------------------------------------------------

.. autofunction:: ffmpegio.ffmpegprocess.run
.. autofunction:: ffmpegio.ffmpegprocess.run_two_pass
.. autoclass:: ffmpegio.ffmpegprocess.Popen
   :members:
