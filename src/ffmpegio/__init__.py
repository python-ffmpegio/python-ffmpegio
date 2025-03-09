from __future__ import annotations

#!/usr/bin/python
# -*- coding: utf-8 -*-
"""FFmpeg I/O interface

Transcode media file to another format/codecs
---------------------------------------------
:py:func:`ffmpegio.transcode()`

Stream Read/Write
-----------------

ffmpegio.open()

Block Read/Write/Filter Functions
---------------------------------

`ffmpegio.video.read()`
`ffmpegio.video.write()`
`ffmpegio.video.filter()`
`ffmpegio.image.read()`
`ffmpegio.image.write()`
`ffmpegio.image.filter()`
`ffmpegio.audio.read()`
`ffmpegio.audio.write()`
`ffmpegio.audio.filter()`
`ffmpegio.media.read()`
"""

import logging

logger = logging.getLogger("ffmpegio")
logger.addHandler(logging.NullHandler())

from . import path, plugins

# register builtin plugins and external plugins found in site-packages
plugins.initialize()

# initialize the paths
try:
    path.find()
except Exception as e:
    logger.warning(str(e))

use = plugins.use


def __getattr__(name):
    if name == "ffmpeg_ver":
        return path.FFMPEG_VER
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


from . import ffmpegprocess

from .errors import FFmpegError, FFmpegioError
from .utils.concat import FFConcat
from .filtergraph import Graph as FilterGraph
from . import devices, ffmpegprocess, caps, probe, audio, image, video, media
from .transcode import transcode
from .utils.parser import FLAG
from ._open import open

# check if ffmpegio-core is installed, if it is warn its deprecation
from ._utils import deprecate_core

deprecate_core()

# fmt:off
__all__ = ["ffmpeg_info", "get_path", "set_path", "is_ready", "ffmpeg", "ffprobe",
    "transcode", "caps", "probe", "audio", "image", "video", "media", "devices",
    "open", "ffmpegprocess", "FFmpegError", "FFmpegioError", "FilterGraph", "FFConcat", "use", "FLAG"]
# fmt:on

__version__ = "0.11.1"

ffmpeg_info = path.versions
set_path = path.find
get_path = path.where
is_ready = path.found
ffmpeg = path.ffmpeg
ffprobe = path.ffprobe
