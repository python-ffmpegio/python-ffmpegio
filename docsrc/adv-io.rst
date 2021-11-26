.. _adv_io:

:py:mod:`ffmpegio.io`: Queue-based nonblocking pipes for FFmpeg data I/O
========================================================================

Python :py:class:`subprocess.Popen` and :py:mod:`io` classes lack ability to 
run subprocess concurrently while constantly exchanging data between Python 
and the subprocess if the subprocess I/O protocol does not have well-defined 
pattern due to the default blocking I/O. To circumvent this issue, 
:py:class:`ffmpegio.ffmpegprocess.Popen` relies on custom stream I/O classes
defined in :py:mod:`ffmpegio.io`:

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.io.QueuedWriter
   ffmpegio.io.QueuedReader
   ffmpegio.io.QueuedLogger

These classes use :py:func:`os.pipe()` configured to do nonblocking read, and
each both read and write data are buffered using :py:class:`queue.Queue` class.
The actual I/O operations are performed in threads to enable concurrent operations
of Python and FFmpeg.

:py:mod:`ffmpegio.io` Module Reference
------------------------------------------

.. autoclass::    ffmpegio.io.QueuedWriter
   :members:
   :inherited-members:
.. autoclass::    ffmpegio.io.QueuedReader
   :members:
   :inherited-members:
.. autoclass::    ffmpegio.io.QueuedLogger
   :members:
   :inherited-members:
