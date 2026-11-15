
.. py:module:: ffmpegio.ffmpegprocess
.. highlight:: python

.. _adv_ffmpeg:

Direct invocation of FFmpeg subprocess (:code:`ffmpegio.ffmpegprocess`)
=======================================================================

Overview
--------

Instead of indirectly calling FFmpeg with :code:`ffmpegio`'s :ref:`Basic I/O Functions <basicio>`, 
you can directly invoke a FFmpeg subprocess with :py:mod:`ffmpegio.ffmpegprocess` module, 
which mocks Python's builtin :py:mod:`subprocess` module.

.. autosummary::
   :nosignatures:
   :recursive:

   run
   run_two_pass
   Popen

While both :py:func:`run` and :py:class:`Popen` 
constructor accepts the :code:`args` argument of Python's :py:func:`subprocess.run` and 
:py:class:`subprocess.Popen` constructor, the FFmpeg command argument can also be specified 
with a Python dict.

:py:func:`run_two_pass` runs FFmpeg twice to perform two-pass video 
encoding. The audio encoding is automatically disabled during the first pass by default. It
also offers a finer control of which options to turn on/off during the first pass.


Specification of FFmpeg Argument dict :code:`ffmpeg_args`
---------------------------------------------------------

FFmpeg command can be invoked directly with :py:func:`run` or 
:py:class:`Popen`. Both of them fully support the FFmpeg command line option
arguments, which can be specified via  as :py:mod:`subprocess` via :code:`ffmpeg_args` 
argument, which may be supplied as a string or a list of strings to be compatible
with :py:mod:`subprocess` in a plain dict object. 

The FFmpeg command line options structure:

.. code-block:: bash

  ffmpeg [global_options] {[input_file_options] -i input_url} ... \
      {[output_file_options] output_url} ... 

All the options and urls are mapped to :code:`ffmpeg_args` by:

.. code-block:: python

  ffmpeg_args = {
      "inputs": [(input_url, input_file_options), ...],
      "outputs": [(output_url, output_file_options), ...],
      "global_options": global_options,
  }

Any Python sequence types may be used in place of the tuples are lists in the above definition.

:code:`input_file_options`, :code:`output_file_options`, and :code:`global_options` are optional. If 
URL does not require any options, set its options to :code:`None`. If no global options, the 
:code:`"global_options"` dict entry may be omitted or set to :code:`None`. 

To specify options, each set of options is a dict with option keys as the dict keys **without** the
leading dash (-). For stream-specific options, the key shall include the full stream specifiers. For 
example, use :code:`"b:v"` as the dict key to specify the video bitrate.

Option values may be given as any Python type, so long as it can be converted to :code:`str` at the
time of the subprocess invocation. If an option does not take any values, then use :code:`None`. For 
any option which can be defined multiple times (e.g., :code:`map`), specify its value as a sequence 
with each of its elements defining a value for each FFmpeg option. Another exception are the filters
(:code:`vf`, :code:`af`, and :code:`filter_complex`) which values may be given with special option 
value structure (to be covered later).

All defined options are passed unchecked to FFmpeg. 

Examples
--------

First, here are how to set up some of the examples in `FFmpeg Documentation <https://ffmpeg.org/ffmpeg.html#Description>`__
for the :code:`ffmpegio`:

.. code-block:: python

  # To set the video bitrate of the output file to 64 kbit/s:
  #   ffmpeg -i input.avi -b:v 64k -bufsize 64k output.avi
  ffmpeg_args = {
      "inputs": [("input.avi", None)],
      "outputs": [("output.avi", {"b:v": "64k", "bufsize": "64k"})],
  }

  # To force the frame rate of the input file (valid for raw formats only) to 1 fps and 
  # the frame rate of the output file to 24 fps:
  #   ffmpeg -r 1 -i input.m2v -r 24 output.avi
  ffmpeg_args = {
      "inputs": [("input.avi", {"r": 1})],
      "outputs": [("output.avi", {"r": 24})],
  }

  # automatic stream selection
  #   ffmpeg -i A.avi -i B.mp4 out1.mkv out2.wav -map 1:a -c:a copy out3.mov
  ffmpeg_args = {
      "inputs": [("A.avi", None), ("B.mp4", None)],
      "outputs": [
          ("out1.mkv", None), 
          ("out2.wav", None),
          ("out3.mov", {"map": "1:a", "c:a": "copy"}),
      ],
  }

  # unlabeled filtergraph outputs
  #   ffmpeg -i A.avi -i C.mkv -i B.mp4 -filter_complex "overlay" out1.mp4 out2.srt
  ffmpeg_args = {
      "inputs": [("A.avi", None), ("C.mkv", None), ("B.mp4", None)],
      "outputs": [
          ("out1.mp4", None), 
          ("out2.srt", None),
      ],
      "global_options": {"filter_complex": "overlay"}
  }

  # labeled filtergraph outputs
  #   ffmpeg -i A.avi -i B.mp4 -i C.mkv -filter_complex "[1:v]hue=s=0[outv];overlay;aresample" \
  #      -map '[outv]' -an        out1.mp4 \
  #                               out2.mkv \
  #      -map '[outv]' -map 1:a:0 out3.mkv
  ffmpeg_args = {
      "inputs": [("A.avi", None), ("B.mp4", None), ("C.mkv", None)],
      "outputs": [
          ("out1.mp4", {"map": "[outv]", "an": None}), 
          ("out2.mkv", None),
          ("out3.mkv", {"map": ("[outv]", "1:a:0")}), 
      ],
      "global_options": {"filter_complex": "[1:v]hue=s=0[outv];overlay;aresample"}
  }


API Reference
-------------

.. autofunction:: run
.. autofunction:: run_two_pass
.. autoclass:: Popen
   :members:
