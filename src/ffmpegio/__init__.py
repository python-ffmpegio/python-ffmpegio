#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
FFmpeg I/O package

ffmpegio.transcode_sync()

ffmpegio.stream.open()
ffmpegio.stream.read()
ffmpegio.stream.write()

underlying 
"""

from .transcode import transcode
from . import caps
from . import probe
from . import audio
from . import image
from . import ffmpeg as _ffmpeg

set_path = _ffmpeg.find

__all__ = ["transcode", "caps", "probe", "set_path", "audio", "image"]
