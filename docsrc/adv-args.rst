.. _adv_args:

Specification of FFmpeg Argument dict :code:`ffmpeg_args`
=========================================================

:py:mod:`ffmpegio` run the FFmpeg subprocess with :py:func:`ffmpegio.ffmpeg.run` or 
:py:func:`ffmpegio.ffmpeg.run_sync`. Both of these functions take an argument 
:code:`ffmpeg_args`, a plain dict object, to define the full FFmpeg command line options:

.. code-block:: bash

  ffmpeg [global_options] {[input_file_options] -i input_url} ... \
      {[output_file_options] output_url} ... 

All the options and urls are mapped to :code:`ffmpeg_args`:

.. code-block:: python

  ffmpeg_args = {
      "inputs": [(input_url, input_file_options), ...],
      "outputs": [(output_url, output_file_options), ...],
      "global_options": global_options,
  }

All options parameters are optional. If URL does not require any options, set its options to :code:`None`. 
If no global options, the :code:`"global_options"` dict entry may be omitted or set to :code:`None`.
Each set of options is a dict with option keys as the dict keys **without** the leading dash (-). For 
stream-specific options, the key shall include the full stream specifiers. For example, use :code:`"b:v"`
as the dict key to specify the video bitrate.

Option values may be given in any type, which get converted to :code:`str` at the time of the subprocess 
invocation. If an option does not take any values, then use :code:`None`. For any option which can be
defined multiple times (e.g., :code:`map`), specify its value as a sequence with each of its elements defining
a value for each FFmpeg option. Another exception are the filters (:code:`vf`, :code:`af`, and :code:`filter_complex`)
which values may be given with special option value structure (to be covered later).

All defined options are passed unchecked to FFmpeg. 

Examples
--------

First, here are how to set up some of the examples in `FFmpeg Documentation <https://ffmpeg.org/ffmpeg.html#Description>`__
for the :py:mod:`ffmpegio`:

.. code-block:: python

  # To set the video bitrate of the output file to 64 kbit/s:
  #   ffmpeg -i input.avi -b:v 64k -bufsize 64k output.avi
  ffmpeg_args = {
      "inputs": [("input.avi", None)],
      "outputs": [("output.avi", {"b:v": "64k", "bufsize": "64k"})],
  }

  # To force the frame rate of the output file to 24 fps:
  #   ffmpeg -i input.avi -r 24 output.avi
  ffmpeg_args = {
      "inputs": [("input.avi", None)],
      "outputs": [("output.avi", {"r": 24})],
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
