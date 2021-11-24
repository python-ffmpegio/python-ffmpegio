#!/usr/bin/python
# -*- coding: utf-8 -*-
"""FFmpeg I/O interface

Transcode media file to another format/codecs
---------------------------------------------
:py:func:`ffmpegio.transcode()`

Stream Read/Write
-----------------
ffmpegio.open()

Block Read/Write Functions
--------------------------
`ffmpegio.video.read()`
`ffmpegio.video.write()`
`ffmpegio.image.read()`
`ffmpegio.image.write()`
`ffmpegio.audio.read()`
`ffmpegio.audio.write()`
`ffmpegio.media.read()`
`ffmpegio.media.write()`
"""

from contextlib import contextmanager

from .transcode import transcode
from . import caps, probe, audio, image, video
from . import ffmpeg as _ffmpeg
from . import streams as _streams

__all__ = ["transcode", "caps", "probe", "set_path", "audio", "image", "video", "open"]
__version__ = "0.0.13"

ffmpeg_info = _ffmpeg.versions
set_path = _ffmpeg.find
get_path = _ffmpeg.where
is_ready = _ffmpeg.found


@contextmanager
def open(
    url,
    mode="",
    rate=None,
    stream_id=None,
    dtype=None,
    shape=None,
    channels=None,
    **kwds,
):
    """Open a multimedia file/stream for read/write

    :param url: URL of the media source/destination
    :type url: str
    :param mode: specifies the mode in which the FFmpeg is used, defaults to None
    :type mode: str, optional
    :param rate: (write specific) frame rate (video write) or sample rate (audio
                 write), defaults to None
    :type rate: Fraction, float, int, or dict, optional
    :param stream_id: (read specific) media stream, defaults to None
    :type stream_id: int or str, optional
    :param dtype: (write specific) input data numpy dtype, defaults to None
    :type dtype: numpy.dtype, optional
    :param shape: (write specific) video frame size (height x width [x ncomponents]),
                  defaults to None
    :type shape: seq of int, optional
    :param channels: (write specific) audio number of channels, defaults to None
    :type channels: int, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    :yields: ffmpegio stream object

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
    'r'   read from url (default)
    'w'   write to url
    'v'   operate on video stream (default)
    'a'   operate on audio stream
    ====  ============================================

    The default mode is dictated by other arguments. 'w' mode is selected if
    rate, dtype, shape, or channels are given (that is, not None). Otherwise, it
    sets to 'r'. If no media type ('v' or 'a') is specified, it selects the first
    stream of the media in read mode. For write mode, media type designation
    is required unless `shape` or `channels` are specified.

    `stream_id` specifies which stream to target. It may be a stream index (int) or
    specific to each media type, e.g., 'v:0' for the first video stream or 'a:2' for
    the 3rd audio stream.

    `rate` is required to write a media stream and specifies the video frame rate
    or audio sample rate. Video frame rate is in frames/second and may be given
    as a number, string, or `fractions.Fraction`. Audio sample rate in
    samples/second (per channel) and shall be given as an integer or string.

    `dtype`, `shape`, and `channels` are specific to the write mode.

    'dtype' is requried and specifies the expected numpy array data type
    (e.g., `numpy.uint8`).

    Optional `shape` defines the video frame size and number of components
    with a 2 or 3 element sequence: `(width, height[, ncomp])`. The number of
    components and `dtype` implicitly define the pixel format:

    =====  ============  =========  ===================================
    ncomp  dtype         pix_fmt    Description
    =====  ============  =========  ===================================
      1    numpy.uint8   gray       grayscale
      1    numpy.uint16  gray16le   16-bit grayscale
      1    numpy.single  grayf32le  floating-point grayscale
      2    numpy.uint8   ya8        grayscale with alpha channel
      2    numpy.uint16  ya16le     16-bit grayscale with alpha channel
      3    numpy.uint8   rgb24      RGB
      3    numpy.uint16  rgb48le    16-bit RGB
      4    numpy.uint8   rgba       RGB with alpha transparency channel
      4    numpy.uint16  rgba64le   16-bit RGB with alpha channel
    =====  ============  =========  ===================================

    For audio output stream, optional `channels` specifies the number of
    channels.

    If `dtype`, `shape`, and `channels` are not specified at the time of
    opening, they are set during the first write operation.

    In addition, `open()` accepts the standard option keyword arguments.

    `open()` yields a ffmpegio's stream object and automatically closes it
    when goes out of the context

    :Example:

    Open an MP4 file and process all the frames::

        with ffmpegio.open('video_source.mp4') as f:
            frame = f.read()
            while frame:
                # process the captured frame data
                frame = f.read()

    Read an audio stream of MP4 file and write it to a FLAC file as samples
    are decoded::

        with ffmpegio.open('video_source.mp4','ra') as rd:
            fs = rd.sample_rate
            with ffmpegio.open('video_dst.flac','wa',rate=fs) as wr:
                frame = rd.read()
                while frame:
                    wr.write(frame)
                    frame = rd.read()

    """

    audio = "a" in mode
    video = "v" in mode
    read = "r" in mode
    write = "w" in mode
    # filter = "f" in mode
    # backwards = "b" in mode
    unk = set(mode) - set("avrw")
    if unk :
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Unknown mode {unk} specified."
        )

    if read + write > 1:  # + filter
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Only 1 of 'rwf' may be specified."
        )

    # if backwards + (write or filter) > 1:
    #     raise Exception(
    #         f"Invalid FFmpeg streaming mode: {mode}. Backward streaming only supported for read stream."
    #     )

    if not (read or write or filter):
        if url:
            read = True  # default to read if url given
        # else:
        #     filter = True  # default to write if no url given

    # if backwards:
    #     raise Exception("Current version does not support backward streaming.")

    # if filter:
    #     raise Exception("Current version does not support filtering")

    if not isinstance(url, str):
        raise Exception("url must be a string")

    # auto-detect
    if not (audio or video):
        if read:
            info = probe.streams_basic(url, entries=("codec_type",))
            if stream_id is None:
                for i, st in enumerate(info):
                    if st["codec_type"] == "video":
                        stream_id = i
                        video = True
                        break
                    elif st["codec_type"] == "audio":
                        stream_id = i
                        audio = True
                        break
            elif stream_id < len(info):
                video = info[stream_id]["codec_type"] == "video"
                audio = info[stream_id]["codec_type"] == "audio"
            else:
                raise Exception(f"invalid stream_id ({stream_id})")

        else:  # write
            # TODO identify based on file extension
            audio = shape is None and channels is not None
            video = not audio

    if video == audio:
        raise Exception(
            "Current version does not support multimedia or multi-stream IO"
        )
    else:
        StreamClass = (
            (_streams.SimpleAudioWriter if write else _streams.SimpleAudioReader)
            if audio
            else (_streams.SimpleVideoWriter if write else _streams.SimpleVideoReader)
        )
        if read:
            kwds["stream_id"] = stream_id or 0
        if write:
            kwds["rate"] = rate
            kwds["dtype"] = dtype
            if video:
                kwds["shape"] = shape
            elif audio:
                kwds["channels"] = channels

    # instantiate the streaming object
    # TODO wrap in try-catch if AV stream fails to try a multi-stream version
    stream = StreamClass(url=url, **kwds)
    try:
        yield stream
    finally:
        # terminate FFmpeg
        stream.close()
