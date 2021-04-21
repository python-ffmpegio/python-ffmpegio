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
def open(
    url,
    mode="",
    stream_id=None,
    rate=None,
    dtype=None,
    shape=None,
    channels=None,
    **kwds,
):
    """open a multimedia file/stream

    :param url: URL of the media source/destination
    :type url: str
    :param mode: specifies the mode in which the FFmpeg is used, defaults to None
    :type mode: str, optional
    :param stream_id: (read specific) media stream, defaults to None
    :type stream_id: int or str, optional
    :param rate: (write specific) frame rate (video write) or sample rate (audio
                 write), defaults to None
    :type rate: Fraction, float, int, or dict, optional
    :param dtype: (write specific) input data numpy dtype, defaults to None
    :type dtype: numpy.dtype, optional
    :param shape: (write specific) video frame size (height x width [x ncomponents]),
                  defaults to None
    :type shape: seq of int, optional
    :param channels: (write specific) audio number of channels, defaults to None
    :type channels: int, optional

    Start FFmpeg and open I/O link to it to perform read/write operation and return
    a corresponding stream object. If the file cannot be opened, an error is raised.
    See Reading and Writing Files for more examples of how to use this function.

    `url` is a string specifying the pathname (absolute or relative to the current working
    directory) of the media target (file or streaming media) to be opened. This argument
    is ignored if FFmpeg is opened in filtering mode

    `mode` is an optional string that specifies the mode in which the FFmpeg is opened.

    ====  ============================================
    Mode  Description
    ====  ============================================
    'r'   read from url
    'w'   write to url
    'v'   operate on video stream
    'a'   operate on audio stream
    ====  ============================================

    The default mode is dictated by other arguments. 'w' mode is selected if 
    rate, dtype, shape, or channels are given (that is, not None). Otherwise, it
    sets to 'r'. If no media type ('v' or 'a') is specified, it selects the first
    stream of the media.

    `stream_id` specifies which stream to target. It may be a stream index (int) or
    specific to each media type, e.g., 'v:0' for the first video stream or 'a:2' for
    the 3rd audio stream. 



    """
    audio = "a" in mode
    video = "v" in mode
    read = "r" in mode
    write = "w" in mode
    filter = "f" in mode
    backwards = "b" in mode
    if unk := set(mode) - set("avrwfb"):
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Unknown mode {unk} specified."
        )

    if read + write + filter > 1:
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Only 1 of 'rwf' may be specified."
        )

    if backwards + (write or filter) > 1:
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Backward streaming only supported for read stream."
        )

    if not (read or write or filter):
        if url:
            read = True  # default to read if url given
        else:
            filter = True  # default to write if no url given

    if backwards:
        raise Exception("Current version does not support backward streaming.")

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
        if video == audio or (stream_ids and len(stream_ids) > 1):
            raise Exception(
                "Current version does not support multimedia or multi-stream IO"
            )
        else:
            StreamClass = (
                (_streams.SimpleAudioWriter if write else _streams.SimpleAudioReader)
                if audio
                else (
                    _streams.SimpleVideoWriter if write else _streams.SimpleVideoReader
                )
            )
            if read:
                kwds["stream_id"] = (stream_ids and stream_ids[0]) or 0
            if write:
                kwds["rate"] = rate

    # instantiate the streaming object
    # TODO wrap in try-catch if AV stream fails to try a multi-stream version
    stream = StreamClass(url=url, **kwds)
    try:
        yield stream
    finally:
        # terminate FFmpeg
        stream.close()
