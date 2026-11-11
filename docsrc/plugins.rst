.. py:module:: ffmpegio.plugins
.. highlight:: python

.. _plugins:

Plugin System (:code:`ffmpegio.plugins`)
========================================

Overview
--------

:code:`ffmpegio` implements a plugin system using Pytest's `pluggy <https://pluggy.readthedocs.io/en/latest/>`_ 
package to provide flexibility to find FFmpeg/FFprobe binaries and to support various raw media data formats.

Functions
---------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.use
   ffmpegio.using
   list_plugins
   register
   unregister

These functions control the plugins.

Plugin Hooks
------------

There are three types of plugins available, each with one or more hooks
to be implemented.

FFmpeg finder hook
^^^^^^^^^^^^^^^^^^

.. autosummary::
   :nosignatures:
   :recursive:

   hookspecs.finder

The first type of hook is a file finder, which returns 
the paths to FFmpeg and FFprobe. There are four built-in plugin 
modules support this type:

.. autosummary::

   finder_syspath
   finder_win32
   finder_ffdl
   finder_static


Raw data reader helper hooks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autosummary::
   :nosignatures:
   :recursive:

   hookspecs.bytes_to_video
   hookspecs.bytes_to_audio
   hookspecs.is_empty

These hooks are used by reader functions to convert 
bytes data from FFmpeg to a Python data type. A custom
plugin may implement only video or audio. 
:py:func:`is_empty <ffmpegio.plugins.hookspecs.is_empty>` must be
implemented for both media types. There are three built-in 
plugin modules support this type:

.. autosummary::

   rawdata_bytes
   rawdata_numpy
   rawdata_pillow

Raw data writer helper hooks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autosummary::
   :nosignatures:
   :recursive:

   hookspecs.video_info
   hookspecs.video_bytes
   hookspecs.video_frames
   hookspecs.audio_info
   hookspecs.audio_bytes
   hookspecs.audio_samples

To write media data, three separate hooks are necessary for each media type.
There are four built-in plugin modules supporting this type:

.. autosummary::

   rawdata_bytes
   rawdata_numpy
   rawdata_mpl
   rawdata_pillow

..
   Device management helper hooks
   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

   .. autosummary::
      :nosignatures:
      :recursive:

      hookspecs.device_source_api
      hookspecs.device_sink_api

How to write your own plugins
-----------------------------

Pluggy offers a flexible plugin system, and custom plugins can be
created at ease. Follow `their documentation <https://pluggy.readthedocs.io/en/latest/>`_
for various ways to implement custom plugins. Note that all the plugin hooks are specified
as first result only, i.e., only the first valid implementation (returning a non-None value)
will be used.

The plugin hooks must follow the specifications defined on this page or in
:code:`ffmpegio.plugins.hookspecs`. Also, when creating a plugin package, declare the
plugin with a project entry point in :code:`[project.entry-points."ffmpegio"]` specifications
of :code:`pyproject.toml` to enable auto-loading of the plugin if it has been installed.

For example, you have compiled FFmpeg and FFprobe binaries
and want to use them without adding them to the system path.
You can write a custom finder plugin module: :code:`find_my_ffmpeg.py`

.. code-block:: python

   from pathlib import Path

   from pluggy import HookimplMarker

   hookimpl = HookimplMarker("ffmpegio")

   __all__ = ["finder"]


   @hookimpl
   def finder() -> tuple[str, str]:
      """find my own ffmpeg and ffprobe binaries"""

      my_dir = Path('~/FFmpeg/').expanduser()

      ffmpeg_path = my_dir / 'ffmpeg'
      ffprobe_path = my_dir / 'ffprobe'

      return (
         (ffmpeg_path, ffprobe_path)
         if ffmpeg_path.exists() and ffprobe_path.exists()
         else None
      )

Then, the plugin can be registered at the top of your script, followed by
:py:func:`ffmpegio.set_path()` to run the FFmpeg binary search again:

.. code-block:: python

   import ffmpegio as ff
   import find_my_ffmpeg

   # register your plugin
   ff.plugins.register(find_my_ffmpeg,'my_ffmpeg_finder')

   # re-run FFmpeg search to reset the paths
   [ffmpeg_path, ffprobe_path, version] = ff.set_path()
   print(f"ffmpegio is using the following binaries: \n\t{ffmpeg_path=}\n\t{ffprobe_path=}\n\t{version=}\n")

If this plugin will be used in multiple Python projects, create a :code:`find_my_ffmpeg` package.
First, move :code:`find_my_ffmpeg.py` to a new Python project folder 
:code:`find_my_ffmpeg/find_my_ffmpeg.py``. And prepare `find_my_ffmpeg/pyproject.toml`: 

.. code-block:: toml

   [project]
   name = "find-my-ffmpeg"
   version = "1.0.0"
   
   [project.entry-points."ffmpegio"]
   find_my_ffmpeg = "find_my_ffmpeg"

This new package can be installed by

.. code-block:: bash

   pip install find_my_ffmpeg

Then, :code:`ffmpegio` will automatically detect this package
and registers the plugin. This means that the plugin will be used
in the initial binary search when the module is loaded and 
explicit call of :py:func:`ffmpegio.set_path()` is no longer required.

References
----------

.. autofunction:: ffmpegio.use
.. autofunction:: ffmpegio.using
.. autofunction:: list_plugins
.. autofunction:: register
.. autofunction:: unregister

Hook Specifications
-------------------

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

..
   .. autofunction:: hookspecs.device_source_api
   .. autofunction:: hookspecs.device_sink_api
