"""ffmpegio plugin to use `numpy.ndarray` objects for media data I/O"""
import logging
from pluggy import HookimplMarker

import ffmpeg_downloader as ffdl

hookimpl = HookimplMarker("ffmpegio")

__version__ = "0.1.1"

__all__ = ["finder"]


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    ffmpeg_path = ffdl.ffmpeg_path

    if ffmpeg_path is None:
        logging.warning(
            """ffmpegio-plugin-downloader is detected but the FFmpeg executables have not been installed. First, run in the terminal:
        
          python -m ffmpeg_downloader

        to download and install the executable. Internet connection is required."""
        )
        return None

    return ffmpeg_path, ffdl.ffprobe_path
