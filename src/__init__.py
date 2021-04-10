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

from .transcode import transcode_sync
from . import caps
from . import probe
from . import ffmpeg as _ffmpeg

__all__ = ["transcode_sync", "caps", "probe"]
