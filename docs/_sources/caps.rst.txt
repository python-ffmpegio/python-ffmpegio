.. _caps:

FFmpeg Capabilities References
==============================

:py:mod:`ffmpegio.caps` module contains a set of functions to wrap ffmpeg's 
help/show commands to check the capabilities of the ffmpeg executable that 
the :py:mod:`ffmpegio` is employing.

.. todo::

   Parsing the additional command options that are specific to the containers, 
   codecs, and filters. The :code:`options` fields are currently returned as
   unparsed :code:`str`


List of Functions
-----------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.caps.options
   ffmpegio.caps.pix_fmts
   ffmpegio.caps.sample_fmts
   ffmpegio.caps.layouts
   ffmpegio.caps.colors
   ffmpegio.caps.filters
   ffmpegio.caps.filter_info
   ffmpegio.caps.codecs
   ffmpegio.caps.encoders
   ffmpegio.caps.encoder_info
   ffmpegio.caps.decoders
   ffmpegio.caps.decoder_info
   ffmpegio.caps.formats
   ffmpegio.caps.muxers
   ffmpegio.caps.muxer_info
   ffmpegio.caps.demuxers
   ffmpegio.caps.demuxer_info
   ffmpegio.caps.bsfilters
   ffmpegio.caps.bsfilter_info
   ffmpegio.caps.devices
   ffmpegio.caps.protocols

.. todo::

   Remaining commands to be wrapped: sources, sinks, h protocol, dispositions


List of Constants
-----------------   

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.caps.video_size_presets
   ffmpegio.caps.frame_rate_presets

Function References
-------------------

.. autofunction:: ffmpegio.caps.options
.. autofunction:: ffmpegio.caps.pix_fmts
.. autofunction:: ffmpegio.caps.sample_fmts
.. autofunction:: ffmpegio.caps.layouts
.. autofunction:: ffmpegio.caps.colors
.. autofunction:: ffmpegio.caps.filters
.. autofunction:: ffmpegio.caps.filter_info
.. autofunction:: ffmpegio.caps.codecs
.. autofunction:: ffmpegio.caps.encoders
.. autofunction:: ffmpegio.caps.encoder_info
.. autofunction:: ffmpegio.caps.decoders
.. autofunction:: ffmpegio.caps.decoder_info
.. autofunction:: ffmpegio.caps.formats
.. autofunction:: ffmpegio.caps.muxers
.. autofunction:: ffmpegio.caps.muxer_info
.. autofunction:: ffmpegio.caps.demuxers
.. autofunction:: ffmpegio.caps.demuxer_info
.. autofunction:: ffmpegio.caps.bsfilters
.. autofunction:: ffmpegio.caps.bsfilter_info
.. autofunction:: ffmpegio.caps.devices
.. autofunction:: ffmpegio.caps.protocols
