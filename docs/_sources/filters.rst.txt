.. highlight:: python
.. _filters:

Filtering Reference
===================

One of the great feature of FFmpeg is the plethora of filters to manipulate video, audio, and subtitle
data. See `<the official FFmpeg Filters Documentation https://ffmpeg.org/ffmpeg-filters.html>` and 
`FFmpeg Wiki Entries on Filtering <https://trac.ffmpeg.org/#Filtering>`.

In addition to all the read and write functions in :py:mod:`ffmpegio` supporting an arbitrary
filter operation so long as it is a single-input-single-output (SISO) filtering, it is also 
equipped with `filter` functions and classes to manipulate `numpy.ndarray` using FFmpeg filters.

Intended use cases for these functionalities are:

- Adding FFmpeg filters to the middle of media processing chain
- Isolated evaluation of FFmpeg filters - Running test data through the filters directly without
  needing to save intermediate data

Filtering, much like reading and writing, can be performed with both batch and stream modes. The batch mode
is faster and a single-function-call operation while the stream mode requires the stream to be opened first
then filtering operation can be performed in a little chunks at a time. Note that the stream-mode filtering
does not guarantee its output chunk size to be consistent even if input data size is fixed. Moreover, audio
filter stream does not produce any output until at least 2 seconds of data are input. So, use it with a care.

Batch Functions
---------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.video.filter
   ffmpegio.image.filter
   ffmpegio.audio.filter

The :code:`filter()` functions in :py:mod:`ffmpegio.video`, :py:mod:`ffmpegio.image`, and 
:py:mod:`ffmpegio.audio` are blocking operations. They take an input data array and produces
an output data array.

The following are examples. 

.. note::
   Note that the input data are loaded with :py:mod:`ffmpegio` only for the illustration purpose. If media data
   loaded with :py:mod:`ffmpegio` read functions need to be filtered, call the read function with 
   :code:`vf` (video or image) or :code:`af` (audio) arguments so the filtered output is obtained
   with a single FFmpeg call. 

Example: Image Scaling
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   Iin = ffmpegio.image.read('ffmpeg-logo.png')

   # reduce the size of the input image Iin
   Iout = ffmpegio.image.filter('scale=iw/2:-1', Iin)


Example: Audio Fading
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   fs_in = 4000
   T = 10
   x = np.ones(fs_in*T,'f4') # only supports single-precision FP

   # add fade in and fade out
   fs_out, y = ffmpegio.audio.filter('afade=t=in:d=1,afade=t=out:st=9:d=1', fs_in, x)



Streaming Classes
-----------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.streams.SimpleVideoFilter
   ffmpegio.streams.SimpleAudioFilter

TODO Additional writeup

:py:class:`FilterGraph` class
-----------------------------

TODO


API Reference
-------------

.. autofunction:: ffmpegio.video.filter
.. autofunction:: ffmpegio.image.filter
.. autofunction:: ffmpegio.audio.filter
.. autoclass:: ffmpegio.streams.SimpleVideoFilter
   :members:
   :inherited-members:
.. autoclass:: ffmpegio.streams.SimpleAudioFilter
   :members:
   :inherited-members:

