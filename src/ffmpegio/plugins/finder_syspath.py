"""ffmpegio plugin to find ffmpeg and ffprobe on system path"""

import logging

from pluggy import HookimplMarker

from shutil import which

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    if which("ffmpeg") and which("ffprobe"):
        return "ffmpeg", "ffprobe"

    logging.warning("""FFmpeg and FFprobe binaries not found in the system path.""")
    return None
