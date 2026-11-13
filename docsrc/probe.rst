.. :py:module:: ffmpegio.probe
.. highlight:: python

.. _probe:

Media Probe Functions (:code:`ffmpegio.probe`)
==============================================

Overview
--------

:code:`ffmpegio.probe` module contains a full-featured ffprobe wrapper function
:py:func:`full_details <ffmpegio.probe.full_details>` and its derivative functions, which are
tailored to retrieve specific type of information from a media file or stream.

List of Functions
-----------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.probe.format_basic
   ffmpegio.probe.streams_basic
   ffmpegio.probe.video_streams_basic
   ffmpegio.probe.audio_streams_basic
   ffmpegio.probe.full_details
   ffmpegio.probe.query
   ffmpegio.probe.frames
   ffmpegio.probe.packets

Argument Type References
------------------------

.. autoclass:: ffmpegio.probe.IntervalSpec
.. autoclass:: ffmpegio.probe.BasicFormatInfoDict
    :members:
    :undoc-members:    
.. autoclass:: ffmpegio.probe.BasicStreamInfoDict
    :members:
    :undoc-members:    
.. autoclass:: ffmpegio.probe.VideoStreamInfoDict
    :members:
    :undoc-members:    
.. autoclass:: ffmpegio.probe.AudioStreamInfoDict
    :members:
    :undoc-members:    

Function References
-------------------

.. autofunction:: ffmpegio.probe.format_basic
.. autofunction:: ffmpegio.probe.streams_basic
.. autofunction:: ffmpegio.probe.video_streams_basic
.. autofunction:: ffmpegio.probe.audio_streams_basic
.. autofunction:: ffmpegio.probe.full_details
.. autofunction:: ffmpegio.probe.query
.. autofunction:: ffmpegio.probe.frames
.. autofunction:: ffmpegio.probe.packets
