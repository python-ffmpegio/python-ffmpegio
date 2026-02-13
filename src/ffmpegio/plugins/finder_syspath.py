"""ffmpegio plugin to find ffmpeg and ffprobe on system path"""

from __future__ import annotations

import logging
from shutil import which

from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    if which("ffmpeg") and which("ffprobe"):
        logging.info("found ffmpeg and ffprobe on the system path")
        return "ffmpeg", "ffprobe"

    logging.warning("""FFmpeg and FFprobe binaries not found in the system path.""")
    return None
