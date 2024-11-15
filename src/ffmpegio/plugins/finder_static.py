"""ffmpegio plugin to find ffmpeg and ffprobe installed by static-ffmpeg package"""

import logging
from pluggy import HookimplMarker
from static_ffmpeg import run

hookimpl = HookimplMarker("ffmpegio")

__all__ = ["finder"]


@hookimpl
def finder():
    """find ffmpeg and ffprobe executables"""

    try:
        paths = run.get_or_fetch_platform_executables_else_raise()
    except Exception as e:
        logging.warn(
            f"""static-ffmpeg binary paths could not be resolved. Error message:
            
              {e}"""
        )
        return None

    return paths
