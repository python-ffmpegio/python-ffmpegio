"""ffmpegio plugin to find ffmpeg and ffprobe installed by ffmpeg-downloader (ffdl) package"""

import logging
from os import path
from pluggy import HookimplMarker

import ffmpeg_downloader as ffdl

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    ffmpeg_path, ffprobe_path = ffdl.ffmpeg_path, ffdl.ffprobe_path

    if path.exists(ffmpeg_path) and path.exists(ffprobe_path):
      return ffmpeg_path, ffprobe_path

    logging.warning(
        """FFmpeg binaries not found in the ffmpeg-downloader's install directory. To install, run the following in the terminal:
    
      ffdl install

    This will download and install the ffmpeg and ffprobe executables. Internet connection is required."""
    )
    
    return None

