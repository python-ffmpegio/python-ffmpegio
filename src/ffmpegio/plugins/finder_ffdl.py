"""find FFmpeg and FFprobe installed by `ffmpeg-downloader <https://github.com/python-ffmpegio/python-ffmpeg-downloader>`_ package

This built-in plugin is only activated if the :code:`ffmpeg_downloader` module is installed in the current Python environment.
If activated, the :py:func:`finder <ffmpegio.plugins.hookspecs.finder>` hook of this built-in plugin module returns the
paths to the ffmpeg and ffprobe that are configured by the `ffmpeg-downloader <https://github.com/python-ffmpegio/python-ffmpeg-downloader>`_ 
package.

.. note::

   By design, :code:`ffmpeg_downloader` does not automatically download the binaries, and it expects the user to run its :code:`ffdl`
   command-line tool to install the ffmpeg & ffprobe in a similar manner as :code:`pip`. Before running Python and :code:`ffmpegio`, run

   .. code-block::

      ffdl install

   to download and install the latest FFmpeg builds to a user directory or

   .. code-block::

      ffdl install 7

   to specify a particular version (:code:`ffdl list` to see the available ffmpeg releases). 
    
   You could upgrade the installed binaries by running :code:`ffdl install -U`.

"""

from __future__ import annotations

import logging
from os import path

import ffmpeg_downloader as ffdl
from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]

logger = logging.getLogger("ffmpegio.plugins")

@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    ffmpeg_path, ffprobe_path = ffdl.ffmpeg_path, ffdl.ffprobe_path

    if (
        ffmpeg_path is not None
        and path.exists(ffmpeg_path)
        and path.exists(ffprobe_path)
    ):
        return ffmpeg_path, ffprobe_path

    logger.warning(
        """FFmpeg binaries not found in the ffmpeg-downloader's install directory. To install, run the following in the terminal:
    
      ffdl install

    This will download and install the ffmpeg and ffprobe executables. Internet connection is required."""
    )

    return None
