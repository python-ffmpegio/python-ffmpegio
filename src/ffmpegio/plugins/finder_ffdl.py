"""ffmpegio plugin to find ffmpeg and ffprobe installed by ffmpeg-downloader (ffdl) package"""

import logging
from pluggy import HookimplMarker

import ffmpeg_downloader as ffdl

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    ffmpeg_path = ffdl.ffmpeg_path

    if ffmpeg_path is None:
        logging.warning(
            """FFmpeg binaries not found in the ffmpegio-downloader's install directory. To install, run the following in the terminal:
        
          ffdl install

        This will download and install the ffmpeg and ffprobe executables. Internet connection is required."""
        )
        return None

    return ffmpeg_path, ffdl.ffprobe_path
