"""ffmpegio plugin to find ffmpeg and ffprobe installed by ffmpeg-downloader (ffdl) package"""

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
