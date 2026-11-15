"""Find FFmpeg and FFprobe on the system path

The :py:func:`finder <ffmpegio.plugins.hookspecs.finder>` hook of this built-in plugin module returns :code:`"ffmpeg"` 
and :code:`"ffprobe"` if both commands are found by :py:func:`shutil.which`.
"""

from __future__ import annotations

import logging
from shutil import which

from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]

logger = logging.getLogger("ffmpegio.plugins")


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    if which("ffmpeg") and which("ffprobe"):
        logger.info("found ffmpeg and ffprobe on the system path")
        return "ffmpeg", "ffprobe"

    logger.warning("""FFmpeg and FFprobe binaries not found in the system path.""")
    return None
