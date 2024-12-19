.. highlight:: python
.. py:currentmodule:: ffmpegio.filtergraph
.. _filtergraph:

*****************************
Filtergraph Builder Reference
*****************************

One of the great feature of FFmpeg is the plethora of filters to manipulate video and audio data. 
See `the official FFmpeg Filters Documentation <https://ffmpeg.org/ffmpeg-filters.html>`_ and 
`FFmpeg Wiki articles on Filtering <https://trac.ffmpeg.org/#Filtering>`_.

All the media I/O operations in :py:mod:`ffmpegio` support FFmpeg filtering via per-stream 
``filter``, ``vf``, ``af``, and ``filter_script`` output options as well as the ``filter_complex`` and 
``filter_complex_script`` global option. These options are typically specified by filtergraph 
expression strings. For example, ``'scale=iw/2:-1'`` to reduce the video frame size by half. Multiple 
operations can be performed in sequence by chaining the filters, e.g., ``'afade=t=in:d=1,afade=t=out:st=9:d=1'``
adds fade-in and fade-out effect to an audio stream. More complex filtergraph with multiple chains
can also be specified, but as the complexity increases the expression length also increases. 
The :py:mod:`ffmpegio.filtergraph` submodule is designed to assist building complex filtergraphs. The 
module serves 3 primary functions:

* :ref:`access`
* :ref:`build`
* :ref:`script`

These functions are served by three classes:

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.filtergraph.Filter
   ffmpegio.filtergraph.Chain
   ffmpegio.filtergraph.Graph

See :ref:`api` section below for the full documentation of these classes
and other helper functions.

All filtergraph classes can be instantiated with a valid filtergraph description string and yield 
filtergraph descriptions when converted to :py:class:`str`.

.. repl::
   
   import ffmpegio.filtergraph as fgb

   # for a simple chain, use either Chain or Graph 
   fgb.Chain('afade=t=in:d=1,afade=t=out:st=9:d=1')
   fgb.Graph('afade=t=in:d=1,afade=t=out:st=9:d=1')

   # construct the chain from filters 
   fgb.Filter('afade=t=in:d=1') + fgb.Filter('afade=t=out:st=9:d=1')


All :py:mod:`ffmpegio` functions that take filter options accept these objects as input arguments
and convert to :py:class:`str` internally:

>>> fs, x = ffmpegio.audio.read('input.mp3', af=fg)
>>> # x contains the audio samples with the fading effects
  
.. note::

   The simplified examples on this pages are for illustration purpose only. If a filtergraph is
   simple and does not require programmatic construction, use plain :py:class`str` expressions to 
   improve the runtime speed.

.. _access:

======================================
Accessing filter information on FFmpeg
======================================

Filters can be instantiated in a several different ways:

* :py:class:`fgb.Filter` constructor with option values as arguments
* :py:class:`fgb.Filter` constructor with a single-filter filtergraph description
* ``fgb.<filter_name>`` dynamic function (where ``<filter_name>>`` is the 
  name of a FFmpeg filter)

For example, a crop filter ``crop=in_w-100:in_h-100:x=100:y=100`` can be created 
by any of the following 3 lines:

.. repl::

   fgb.Filter('crop', 'in_w-100', 'in_h-100', x=100, y=100)
   fgb.Filter('crop=in_w-100:in_h-100:x=100:y=100')
   fgb.crop('in_w-100', 'in_h-100', x=100, y=100)

The :py:func`fgb.crop` function is dynamically created when user call it for the
first time. If the function name fails to resolve an FFmpeg filter, an
:py:exc:`AttributeError` will be raised.

In addition, these dynamic functions get FFmpeg filter help text as their docstrings:

.. repl::
   
   help(fgb.crop)

Use :py:func:`ffmpegio.caps.filters` to get the full list of filters supported by the installed 
FFmpeg and :py:func:`ffmpegio.caps.filter_info` to get a parsed version of the filter help text.

.. _build:

=========================
Constructing filtergraphs
=========================

A complex filtergraph can be authored using a combination of :py:class:`Filter`, :py:class:`Chain`, 
and :py:class:`Graph`. The following 4 operators are defined:

========  ===========
Operator  Description
========  ===========
 ``|``    Stack sections (no linking)
 ``* n``  Create ``n`` copies of itself and stack them
 ``+``    Join filtergraph sections
 ``>>``   Point-to-point connection and pad labeling
========  ===========

Other useful filtergraph manipulation class methods are:

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.filtergraph.Filter.apply
   ffmpegio.filtergraph.Chain.append
   ffmpegio.filtergraph.Chain.extend
   ffmpegio.filtergraph.Graph.link
   ffmpegio.filtergraph.Graph.add_label
   ffmpegio.filtergraph.Graph.stack
   ffmpegio.filtergraph.Graph.connect
   ffmpegio.filtergraph.Graph.join
   ffmpegio.filtergraph.Graph.attach
   ffmpegio.filtergraph.Graph.rattach

This section mainly describes the operators, leaving the details of the class methods to the API
reference section later on this page.

``|``: filtegraph stacking
--------------------------

Stacking operation creates a new :py:class:`Graph` object from two filtergraph objects, orienting
them in parallel without making any connections. The left and right sides do not need to be of the  
same class, and they can be mixed and matched.

.. repl::

   # 1. given 2 filters
   fgb.trim(30, 60) | fgb.trim(90, 120)

   # 2. given 2 chains
   fgb.Chain('trim=30:60,scale=200:-1') | fgb.Chain('atrim=30:60,afade=t=in')

   # 3. given 2 graphs
   fgb.Graph('[0:v]trim=30:60,scale=200:-1[out]') | fgb.Graph('[0:a]atrim=30:60,afade=t=in[out]')


.. note::

   Duplicate link labels are automatically renamed with a trailing counter.


``* n``: filtergraph self-stacking
----------------------------------

Like Python lists and tuples, multipling any :py:mod:`filtergraph` object by an integer creates a
:py:class:`Graph` object containing ``n`` copies of the object and stack them (i.e., create parallel 
chains).

.. repl::

   # multiplying filters
   fgb.crop(100,100) * 3 

   # multiplying chains
   fgb.Chain('fps=30,format=yuv420p') * 2 

   # multiplying graphs
   fgb.Graph('color,[0]overlay[vout]') * 2 

.. note::

   Multiplied link labels receive unique labels with trailing counter.

``+``: filtergraph joining
--------------------------

Join operation connects two :py:mod:`filtergraph` objects by auto-linking the available output
pads of the left side and the available input pads of the right side. The output object type depends
on the input types.

Joining a single-output object to a single-input object connection is trivial. If both are of either 
:py:class:`Filter` or :py:class:`Chain` classes, they are joined in series, resulting in 
:py:class:`Chain` object. If :py:class:`Graph` is involved, the joining chain is extended with the
other object.

.. repl::

   # 1. joining 2 filters:
   fgb.trim(60,120) + fgb.Chain('crop=100:100:12:34,fps=30')

   # 2. joining 2 graphs:
   fgb.Graph('[0]fps=30[v0];[v0]overlay') + fgb.Graph('split[v0][v1];[v1]hflip')
   
Joining multiple-output :py:class:`Graph` object with multiple-input :py:class:`Graph` object yields
a :py:class:`Graph` object. The number of exposed filter pads must match on both sides. The pad
pairing is automatically performed in one of the two possible ways:

1. pairs the first unused output filter pad of each chain of the left filtergraph and the
    first unused input filter pad of each chain of the right filtergraph (per-chain)
2. pairs all the unused filter pads of the left and right filtergraphs (all)

Both pairing types require the two sides to have the matching number of unused pads. If no match is
attained per chain, then the all unused pads are paired. This mechanism allows the ``+`` operator to 
support two important usecases involving branching and merging filters such as ``overlay``, 
``concat``, ``split``, and ``asplit``. The following examples demonstrate these cases:

.. repl::

   # case 1: attaching a chain of one side to one of the multiple pads of the other
   fgb.hflip() + fgb.hstack()

   # case 2: connecting all the chains (one unused pad each) of one side to a filter with 
   #         matching number of pads on the other side
   (fgb.hflip() | fgb.vflip()) + fgb.hstack()
 
.. note::
   If joining results in a multi-chain filtergraph, inter-chain links are *unnamed*, and when 
   converted to :py:class:``str`` the unnamed links uses ``L#`` link names.

.. note::
   Be aware of `the operator precedence <https://docs.python.org/3/reference/expressions.html#operator-precedence>`_.
   That is, ``*`` precedes ``+``, and ``+`` precedes ``|``.

When joining filtergraph objects with multiple inputs and outputs, ``+``

:py:obj:`>>` filtergraph labeling / filtergraph p2p linking
-----------------------------------------------------------

The :py:obj:`>>` is a multi-purpose operator to label a filter pad and to stack two filtergraphs
with a single link between them. It also accepts optionally explicit filter pad id's to override the
default selection policty of the first unused filter pad. 

Simple usecases are:

.. repl::

   # label input and output pads to a SISO filtergraph
   '[in]' >> fgb.scale(100,-2) >> '[out]' 

   # connect 2 filtergraphs with the first available filter pads
   fgb.hflip() >> fgb.concat()

Filter pad labeling
^^^^^^^^^^^^^^^^^^^

To label a filter pad, the label string must be fully specified with the square brackets:

.. code-block:: python

   # valid label strings
   '[in]' >> fg   # valid FFmpeg link label (alphanumeric characters + '_' inside '[]')
   '[0:v]' >> fg  # valid FFmpeg stream specifier (the first video stream of the first input url)
    
   # incorrect label strings
   'in' >> fg  # create an "in" Filter object (not a valid FFmpeg filter)
   '0:v' >> fg # fails to parse the string as a filtergraph

To label multiple pads at once, provide a sequence of labels:

.. repl::

   ['[0:v]','[1:v]'] >> fgb.Chain('overlay,split') >> ['[vout1]','[vout2]']

The pads do not need to be of the same filter:

.. repl::

   ['[0:v]','[1:v]'] >> fgb.Graph('pad=640:480[v1];scale=100:100[v2];[v1][v2]overlay')

Filtergraph linking
^^^^^^^^^^^^^^^^^^^

Functionally, :py:obj:`>>` and :py:obj:`+` are the same if both sides of the operator expose only
one pad. So, they can be used interchangeably.

.. repl::

   # following two operations produce the same filtergraph
   fgb.hflip() >> fgb.vflip()
   fgb.hflip() + fgb.vflip()
   
The :py:obj:`>>` operator is primarily designed to attach a filter or a filterchain to a larger 
filtergraph with multiple pads.

.. repl::

   # a 4-input graph with the first one connected to an input stream
   fg = fgb.Graph('[0:v]hstack[h1];hstack[h2];[h1][h2]vstack')

   # add the zoomed version as the second input
   fgb.Graph('[0:v]crop,scale') >> fg 
   # -> [0:v]crop,scale[L1];[0:v][L1]hstack[h1];hstack[h2];[h1][h2]vstack

Filter pad indexing
^^^^^^^^^^^^^^^^^^^

In some cases linking of the filter pads may not happen in a top-down order. It is also possible to
specify which filter pad to label or to connect.

First, here is the the automatic pad selection rules:

- Unused filter pad is searched on filterchains in sequence
- On the selected filterchain on the left side of :py:obj:`>>`

  * The first filter with an unused input pad is selected
  * The first unused input pad on the selected filter is selected

- On the selected filterchain on the right side of :py:obj:`>>` 

  * The last filter with an unused output pad is selected
  * The first unused output pad on the selected filter is selected

These rules apply to both labeling and linking. Here are a couple examples to illustrate
the order of pad selection:

.. repl::

   ["[in1]", "[in2]", "[in3]", "[in4]"] >> fgb.Graph("overlay,overlay;hflip")

   fgb.Chain("split,split") >> "[label1]" >> "[label2]" >> "[label3]"


To specify the connecting pads, accompany the label or attaching filtergraph with
the filter pad index:

.. repl::

   ("[in]", (0,1,1)) >> fgb.Graph("overlay,overlay;hflip")

   fgb.Chain("split,split") >> ((0,-1,1), "[label]")

The filter pad index is given by a three-element :py:obj:`tuple`:

.. code-block:: python

   # filter pad index (tuple of 3 ints)
    
   (i, j, k)
   # i -> chain index, selecting the (i+1)st chain
   # j -> filter index on the (i+1)st chain
   # k -> (input or output) pad index of the (j+1)st filter

So, the first example ``(0,1,1)`` selects the 1st chain's 2nd filter (``overlay``) 
and label its 2nd input pad ``[in3]``. Negative indices (as used for Python 
sequences) are supported. The second example ``(0,-1,1)`` selects 
the 1st chain's last filter and labels its 2nd output as ``[label3]``.

Alternatively, an existing label could be used to specify the connecting pad:

.. repl::

   fg_overlay = fgb.Chain("scale=240:-2,format=gray")
   fg1 = fgb.Graph("[in1][in2]overlay,[in3]overlay;[in4]hflip")

   (fg_overlay,'in2') >> fg1
   
The label name for indexing may optionally omit the square brackets as done in this example.

:py:func:`Graph.link` - within-filtergraph linking
--------------------------------------------------

To create a link within a filtergraph, use :py:func`link`. An example in which an intra-graph linking 
is with ``scale2ref``. Its 2 outputs (scaled and passthrough reference streams) may not be used in 
the output pad order. Suppose we want the output video to show the first input on top of the scaled
version of the second input, the desired filtergraph expression is

.. code-block::

   [1:v][0:v]scale2ref[v1_scaled][v0];[v0][v1_scaled]vstack

Neither joining nor linking operation cannot produce the desired outcome:

.. repl::

   #INCORRECT: only one link which is incorrect
   fgb.Graph('[1:v][0:v]scale2ref[v1_scaled][v0]') + fgb.vstack()

   #INCORRECT: correct first link but only one link
   fgb.Graph('[1:v][0:v]scale2ref[v1_scaled][v0]') >> ('v0', fgb.vstack())

To make the explicit link. Use the :py:func:`Graph.link` method to create out-of-order links:

.. repl::

   # first stack 2 filters
   fg = fgb.Graph("[1:v][0:v]scale2ref[v1_scaled][v0]") | fgb.vstack()
   # then make the connections (returns the link label)
   fg.link((-1, 0, 0), "v0") # (-1, 0, 0) <- [v0]
   fg.link((-1, 0, 1), "v1_scaled") # (-1, 0, 1) <- [v1_scaled]
   fg

This method modifies the filtergraph.


Examples
--------

Simple example
^^^^^^^^^^^^^^

Borrowing `the example from ffmpeg-python package <https://github.com/kkroening/ffmpeg-python#complex-filter-graphs>`_:

.. code-block:: bash

  [0]trim=start_frame=10:end_frame=20[v0]; \
  [0]trim=start_frame=30:end_frame=40[v1]; \
  [1]hflip[v2]; \
  [v0][v1]concat=n=2[v3]; \
  [v3][v2]overlay=eof_action=repeat, drawbox=50:50:120:120:red:t=5[v5]

This filtergraph can be built in the following steps:

.. repl::

   v0 = "[0]" >> fgb.trim(start_frame=10, end_frame=20)
   v1 = "[0]" >> fgb.trim(start_frame=30, end_frame=40)
   v3 = "[1]" >> fgb.hflip()
   v2 = (v0 | v1) + fgb.concat(2)
   v5 = (v2|v3) + fgb.overlay(eof_action='repeat') + fgb.drawbox(50, 50, 120, 120, 'red', t=5)
   v5
   
   
Concat with preprocessing stage
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``concat`` filter can be finicky, requiring all the streams to have the same attributes. To combine
mismatched streams, they need to be preprocessed by other filters. Video streams must have the same 
frame size, frame rate, and pixel format. Meanwhile, the audio streams need to have the same sampling
rate, channel format, and sample format.

To build the filtergraph to concatenate mismatched video files, we start by defining the filters

.. repl::

   audio_filter = fgb.aformat(sample_fmts='flt',        # 32-bit floating point format
                              sample_rates=48000,       # 48 kS/s sampling rate
                              channel_layouts='stereo') # 2 channels in stereo layout
   video_filters = [
      fgb.scale(1280, 720, 
                force_original_aspect_ratio='decrease'), # scale at least one dimension to 720p
      fgb.pad(1280, 720, -1, -1),                        # if not 16:9, pad to fill the frame
      fgb.setsar(1),                                     # make sure pixels are square
      fgb.fps(30),                                       # set framerate to 30 (dupe or drop frames)
      fgb.format('yuv420p')                              # use yuv420p pixel format
   ]
   
We need multiple video filters while the ``aformat`` filter takes care of the audio stream format. 
To combine the video filters, we can use the built-in :py:func:`sum` with an empty :py:class:``Filter``.
as the initial value. Then, stack video and audio filters to finalize the preprocessor filtergraph
for an input file.

.. repl::

   preproc = sum(video_filters, fgb.Chain()) | audio_filter
   preproc

Suppose that we have 3 video files, we need 3 copies of the preprocessor filtergraph. The preprocessor
filtergraph can be multiplied 3 times and assign the input stream specs:

.. repl::

   inputs = [f'[{file_id}:{media_type}]' for file_id in range(3) for media_type in ('v', 'a')]
   inputs
   prestage = inputs >> (preproc * 3)
   prestage

Finally, feed the outputs of the prestage filtergraph to the ``concat`` filter and assign the output 
labels:

.. repl::

   fg = prestage + fgb.concat(n=3, v=1, a=1) >> ['[vout]','[aout]']
   fg

Note that the output pads of the ``concat`` filter are listed as "available" because they are 
technically not (yet) connected to anything. You can use this filter graph with :py:func:`ffmpegio.transcode`
to concatenate 3 input MP4 files:

>>> ffmpegio.transcode(['input1.mp4','input2.mp4','input3.mp4'], 'output.mp4',
...                    filter_complex=fg, map=['[vout]','[aout]'])


.. _script:

============================================================
Generating filtergraph script for extremely long filtergraph
============================================================

Extremely long filtergraph description may hit the limit of the subprocess argument length (~30 kB 
for Windows and ~100 kB for Posix). In such case, the filtergraph description needs to be passed to
FFmpeg by the `filter_script` FFmpeg output option or the `filter_complex_script` global option
with a filtergraph script file.

A preferred way to pass a long filtergraph description is to pipe it directly. If ``stdin`` is
available, use the ``input`` argument of :py:func:`subprocess.Popen`:

.. code-block:: python

   # assume `fg` is a SISO video Graph object

   ffmpegio.ffmpegprocess.run(
      {
         'inputs':  [('input.mp4', None)]
         'outputs': [('output.mp4', {'filter_script:v': 'pipe:0'})]
      },
      input=str(fg))

Note that ``pipe:0`` must be used and not the shorthand ``'-'`` unlike
the input url.

If ``stdin`` is not available, :py:func:`Graph.as_script_file` provides a convenient way to create a
temporary script file. The previous example can also run as follows:

.. code-block:: python

   with fg.as_script_file() as script_path:
      ffmpegio.ffmpegprocess.run(
         {
               'inputs':  [('input.mp4', None)]
               'outputs': [('output.mp4', {'filter_script:v': script_path})]
         })


.. _api:

=========================
Filtergraph API Reference
=========================

.. autofunction:: ffmpegio.filtergraph.as_filter
.. autofunction:: ffmpegio.filtergraph.as_filterchain
.. autofunction:: ffmpegio.filtergraph.as_filtergraph
.. autofunction:: ffmpegio.filtergraph.as_filtergraph_object
.. autoclass:: ffmpegio.filtergraph.Filter
   :members:
   :inherited-members:
.. autoclass:: ffmpegio.filtergraph.Chain
   :members:
   :inherited-members:
.. autoclass:: ffmpegio.filtergraph.Graph
   :members:
   :inherited-members:
