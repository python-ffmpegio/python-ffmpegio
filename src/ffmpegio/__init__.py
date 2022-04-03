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

from contextlib import contextmanager
import logging

from . import path, plugins

# register builtin plugins and external plugins found in site-packages
plugins.initialize()

# initialize the paths
try:
    path.find()
except Exception as e:
    logging.warning(str(e))


from . import ffmpegprocess

from .utils.error import FFmpegError
from .utils.concat import FFConcat
from .utils.filter import FilterGraph
from . import devices, ffmpegprocess, caps, probe, audio, image, video, media
from .transcode import transcode
from . import streams as _streams

# fmt:off
__all__ = ["ffmpeg_info", "get_path", "set_path", "is_ready", "ffmpeg", "ffprobe",
    "transcode", "caps", "probe", "audio", "image", "video", "media", "devices",
    "open", "ffmpegprocess", "FFmpegError", "FilterGraph", "FFConcat"]
# fmt:on

__version__ = "0.5.0"

ffmpeg_info = path.versions
set_path = path.find
get_path = path.where
is_ready = path.found
ffmpeg = path.ffmpeg
ffprobe = path.ffprobe


@contextmanager
def open(
    url_fg,
    mode="",
    rate=None,
    shape=None,
    rate_in=None,
    shape_in=None,
    **kwds,
):
    """Open a multimedia file/stream for read/write

    :param url_fg: URL of the media source/destination for file read/write or filtergraph definition
                   for filter operation.
    :type url_fg: str or seq(str)
    :param mode: specifies the mode in which the FFmpeg is used, defaults to None
    :type mode: str, optional
    :param rate: (filter specific) output frame rate (video write) or sample rate (audio
                 write), defaults to None
    :type rate: Fraction, float, int, optional
    :param dtype: (read and filter specific) output data type, defaults to None
    :type dtype: str, optional
    :param shape: (read and filter specific) output video frame size (height x width [x ncomponents]),
                  or audio sample size (channels,), defaults to None
    :type shape: seq of int, optional
    :param rate_in: (filter specific) input frame rate (video write) or sample rate (audio
                 write), defaults to None
    :type rate_in: Fraction, float, int, optional
    :param dtype_in: (write and filter specific) input data type, defaults to None
    :type dtype_in: str, optional
    :param shape_in: (write and filter specific) input video frame size (height x width [x ncomponents]),
                  or audio sample size (channels,), defaults to None
    :type shape_in: seq of int, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional
    :yields: ffmpegio stream object

    Start FFmpeg and open I/O link to it to perform read/write/filter operation and return
    a corresponding stream object. If the file cannot be opened, an error is raised.
    See Reading and Writing Files for more examples of how to use this function.

    `open()` yields a ffmpegio's stream object and automatically closes it
    when goes out of the context

    :Examples:

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
            with ffmpegio.open('video_dst.flac','wa',rate_in=fs) as wr:
                frame = rd.read()
                while frame:
                    wr.write(frame)
                    frame = rd.read()

    :Additional Notes:

    `url_fg` can be a string specifying either the pathname (absolute or relative to the current
    working directory) of the media target (file or streaming media) to be opened or a string describing
    the filtergraph to be implemented. Its interpretation depends on the `mode` argument.

    `mode` is an optional string that specifies the mode in which the FFmpeg is opened.

    ====  ===================================================
    Mode  Description
    ====  ===================================================
    'r'   read from url (default)
    'w'   write to url
    'f'   filter data defined by fg
    'v'   operate on video stream, 'vv' if multi-video reader
    'a'   operate on audio stream, 'aa' if multi-audio reader
    ====  ===================================================

    The default operating mode is dictated by `rate` and `rate_in` arguments. The 'f' mode is selected
    if both `rate` and  `rate_in` are given while the 'w' mode is selected if only `rate_in` without
    `rate` argument is given. Otherwise, it defaults to 'r'.

    If no media type ('v' or 'a') is specified, it selects the first stream of the media in read mode.
    For write and filter modes, the length of `shape_in` if given will be used for the detection:
    'a' if 1 else 'v'. If cannot be autodetected, ValueError will be raised.

    `rate` and `rate_in`: Video frame rates shall be given in frames/second and
    may be given as a number, string, or `fractions.Fraction`. Audio sample rate in
    samples/second (per channel) and shall be given as an integer or string.

    Optional `shape` or `shape_in` for video defines the video frame size and
    number of components with a 2 or 3 element sequence: `(width, height[, ncomp])`.
    The number of components and other optional `dtype` (or `dtype_in`) implicitly
    define the pixel format (FFmpeg pix_fmt option):

    =====  =====  =========  ===================================
    ncomp  dtype  pix_fmt    Description
    =====  =====  =========  ===================================
      1     \|u8   gray       grayscale
      1     <u2   gray16le   16-bit grayscale
      1     <f4   grayf32le  floating-point grayscale
      2     \|u1   ya8        grayscale with alpha channel
      2     <u2   ya16le     16-bit grayscale with alpha channel
      3     \|u1   rgb24      RGB
      3     <u2   rgb48le    16-bit RGB
      4     \|u1   rgba       RGB with alpha transparency channel
      4     <u2   rgba64le   16-bit RGB with alpha channel
    =====  =====  =========  ===================================

    For audio stream, single-element seq argument, `shape` or `shape_in`,
    specifies the number of channels while `dtype` and `dtype_in` determines
    the sample format (FFmpeg sample_fmt option):

    ======  ==========
    dtype   sample_fmt
    ======  ==========
     \|u1     u8
     <i2     s16
     <i4     s32
     <f4     flt
     <f8     dbl
    ======  ==========

    If dtypes and shapes are not specified at the time of opening, they will
    be set during the first write/filter operation using the input data.

    In addition, `open()` accepts the standard option keyword arguments.

    """

    is_fg = isinstance(url_fg, FilterGraph)
    if isinstance(url_fg, str):
        is_fg = kwds.get("f_in", None) == "lavfi"
        url_fg = (url_fg,)

    audio = "a" in mode
    video = "v" in mode
    read = "r" in mode
    write = "w" in mode
    filter = "f" in mode
    # backwards = "b" in mode
    unk = set(mode) - set("avrwf")
    if unk:
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Unknown mode {unk} specified."
        )

    if read + write + filter > 1:
        raise Exception(
            f"Invalid FFmpeg streaming mode: {mode}. Only 1 of 'rwf' may be specified."
        )

    # auto-detect operation
    if not (read or write or filter):
        if rate_in is None:
            read = True
        elif rate is None:
            write = True
        else:
            filter = True

    # auto-detect type
    if not (audio or video):
        if is_fg:
            raise ValueError(
                "media type must be specified to read from an Input filtergraph"
            )
        elif read:
            for url in url_fg:
                try:
                    info = probe.streams_basic(url, entries=("codec_type",))
                except:
                    raise ValueError(f"cannot auto-detect media type of {url}")
                for inf in info:
                    t = inf["codec_type"]
                    if t == "video" and not video:
                        video = True
                    elif t == "audio" and not audio:
                        audio = True
                if video and audio:
                    break

        else:
            if shape_in is not None:
                audio = len(shape_in) < 2
            elif shape is not None:
                audio = len(shape) < 2
            else:
                # TODO identify based on file extension
                raise ValueError(f"cannot auto-detect media type")
            video = not audio
    elif read:
        # if audio or video is set multiple times, use avi reader
        if audio and not video:
            video = audio and sum((1 for m in mode if m == "a")) > 1
        elif video and not audio:
            audio = video and sum((1 for m in mode if m == "v")) > 1
    elif write and is_fg:
        ValueError("Cannot write to a filtergraph.")

    try:
        StreamClass = {
            1: {
                0: _streams.SimpleAudioReader,
                1: _streams.SimpleAudioWriter,
                2: _streams.SimpleAudioFilter,
            },
            2: {
                0: _streams.SimpleVideoReader,
                1: _streams.SimpleVideoWriter,
                2: _streams.SimpleVideoFilter,
            },
            3: {
                0: _streams.AviMediaReader,
            },
        }[audio + 2 * video][write + 2 * filter]
    except:
        raise Exception(f"Invalid/unsupported FFmpeg streaming mode: {mode}.")

    if len(url_fg) > 1 and not StreamClass.multi_read:
        raise Exception(f'Multi-input streaming is not supported in "{mode}" mode')

    # add other info to the arguments
    args = (*url_fg,) if read else (*url_fg, rate_in)
    for k, v in (
        ("rate", rate),
        ("shape", shape),
        ("shape_in", shape_in),
    ):
        if v is not None:
            kwds[k] = v

    # instantiate the streaming object
    # TODO wrap in try-catch if AV stream fails to try a multi-stream version
    stream = StreamClass(*args, **kwds)
    try:
        yield stream
    finally:
        # terminate FFmpeg
        stream.close()
