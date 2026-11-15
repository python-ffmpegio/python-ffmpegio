"""find FFmpeg and FFprobe installed by `static-ffmpeg <https://github.com/zackees/static_ffmpeg>`_ package

This built-in plugin is only activated if the :code:`static_ffmpeg` module is installed in the current Python environment.
If activated, the :py:func:`finder <ffmpegio.plugins.hookspecs.finder>` hook of this built-in plugin module returns the
paths to the ffmpeg and ffprobe that are downloaded and configured by the :code:`static_ffmpeg` package.
"""

from __future__ import annotations

import logging

from pluggy import HookimplMarker
from static_ffmpeg import run

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]

logger = logging.getLogger("ffmpegio.plugins")


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    try:
        paths = run.get_or_fetch_platform_executables_else_raise()
    except Exception as e:
        logger.warn(
            f"""static-ffmpeg binary paths could not be resolved. Error message:
            
              {e}"""
        )
        return None

    return paths
