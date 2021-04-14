#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
FFmpeg I/O package

Transcode media file to another format/codecs
---------------------------------------------
ffmpegio.transcode()

Simple Read/Write Streams
-------------------------
ffmpegio.open()

Simple Read/Write Functions
---------------------------
ffmpegio.video.read()
ffmpegio.video.write()
ffmpegio.image.read()
ffmpegio.image.write()
ffmpegio.audio.read()
ffmpegio.audio.write()
ffmpegio.media.read()
ffmpegio.media.write()
"""

from contextlib import contextmanager

from .transcode import transcode
from . import caps, probe, audio, image, video
from . import ffmpeg as _ffmpeg
from . import streams as _streams

set_path = _ffmpeg.find

__all__ = ["transcode", "caps", "probe", "set_path", "audio", "image", "video", "open"]


@contextmanager
def open(url=None, mode="", **kwds):
    audio = "a" in mode
    video = "v" in mode
    read = "r" in mode
    write = "w" in mode
    filter = "f" in mode
    backwards = "b" in mode

    if read + write + filter > 1:
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Only 1 of 'rwf' may be specified."
        )

    if not (read or write or filter):
        if url:
            read = True  # default to read if url given
        else:
            filter = True  # default to write if no url given

    if filter:
        raise Exception("Current version does not support filtering")
    else:
        if not (audio or video) and url is not None:
            info = probe.streams_basic(url)
            for st in info:
                if st["codec_type"] == "video":
                    video = True
                elif st["codec_type"] == "audio":
                    audio = True
        if video == audio:
            raise Exception("Current version does not support multimedia IO")
        else:
            StreamClass = (
                (_streams.SimpleAudioWriter if write else _streams.SimpleAudioReader)
                if audio
                else (
                    _streams.SimpleVideoWriter if write else _streams.SimpleVideoReader
                )
            )

    # instantiate the streaming object
    # TODO wrap in try-catch if AV stream fails to try a multi-stream version
    stream = StreamClass(url=url, **kwds)
    try:
        yield stream
    finally:
        # terminate FFmpeg
        stream.close()
