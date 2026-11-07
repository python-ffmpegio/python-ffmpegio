.. py:module:`ffmpegio.plugins`

.. _plugins:

Plugin System (``ffmpegio.plugins``)
====================================

:py:mod:`ffmpegio` implements a plugin system using Pytest's `pluggy <https://pluggy.readthedocs.io/en/latest/>`_ 
package to provide flexibility to find FFmpeg/FFprobe binaries and to support various raw media data formats.

Plugin Functions
----------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.use
   ffmpegio.using
   ffmpegio.plugins.list_plugins
   ffmpegio.plugins.register
   ffmpegio.plugins.unregister

Plugin Hook Specifications
--------------------------

There are 12 plugin hooks available in :py:mod:`ffmpegio` and each 

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.plugins.hookspecs.finder
   ffmpegio.plugins.hookspecs.video_info
   ffmpegio.plugins.hookspecs.audio_info
   ffmpegio.plugins.hookspecs.video_bytes
   ffmpegio.plugins.hookspecs.audio_bytes
   ffmpegio.plugins.hookspecs.video_frames
   ffmpegio.plugins.hookspecs.audio_samples
   ffmpegio.plugins.hookspecs.bytes_to_video
   ffmpegio.plugins.hookspecs.bytes_to_audio
   ffmpegio.plugins.hookspecs.is_empty
   ffmpegio.plugins.hookspecs.device_source_api
   ffmpegio.plugins.hookspecs.device_sink_api

Each of these hooks 

References
----------

.. autofunction:: ffmpegio.plugins.hookspecs.finder
.. autofunction:: ffmpegio.plugins.hookspecs.video_info
.. autofunction:: ffmpegio.plugins.hookspecs.audio_info
.. autofunction:: ffmpegio.plugins.hookspecs.video_bytes
.. autofunction:: ffmpegio.plugins.hookspecs.audio_bytes
.. autofunction:: ffmpegio.plugins.hookspecs.video_frames
.. autofunction:: ffmpegio.plugins.hookspecs.audio_samples
.. autofunction:: ffmpegio.plugins.hookspecs.bytes_to_video
.. autofunction:: ffmpegio.plugins.hookspecs.bytes_to_audio
.. autofunction:: ffmpegio.plugins.hookspecs.is_empty
.. autofunction:: ffmpegio.plugins.hookspecs.device_source_api
.. autofunction:: ffmpegio.plugins.hookspecs.device_sink_api

