import numpy as np
from . import ffmpegprocess, utils, configure, filter_utils


def create(name, *args, duration=1.0, progress=None, show_log=None, **kwargs):
    """Create a video using a source video filter

    :param name: name of the source filter
    :type name: str
    :param \\*args: filter arguments
    :type \\*args: tuple, optional
    :param duration:
    :type duration: int
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param capture_log: True to capture log messages on stderr, False to send
                    logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param \\**options: filter keyword arguments
    :type \\**options: dict, optional
    :return: video data
    :rtype: numpy.ndarray

    Supported Video Source Filters
    ------------------------------

    =============  ==============================================================================
    filter name    description
    =============  ==============================================================================
    "color"        uniformly colored frame
    "allrgb"       frames of size 4096x4096 of all rgb colors
    "allyuv"       frames of size 4096x4096 of all yuv colors
    "gradients"    several gradients
    "mandelbrot"   Mandelbrot set fractal
    "mptestsrc"    various test patterns of the MPlayer test filter
    "life"         life pattern based on John Conway’s life game
    "haldclutsrc"  identity Hald CLUT
    "testsrc"      test video pattern, showing a color pattern
    "testsrc2"     another test video pattern, showing a color pattern
    "rgbtestsrc"   RGB test pattern useful for detecting RGB vs BGR issues
    "smptebars"    color bars pattern, based on the SMPTE Engineering Guideline EG 1-1990
    "smptehdbars"  color bars pattern, based on the SMPTE RP 219-2002
    "pal100bars"   a color bars pattern, based on EBU PAL recommendations with 100% color levels
    "pal75bars"    a color bars pattern, based on EBU PAL recommendations with 75% color levels
    "yuvtestsrc"   YUV test pattern. You should see a y, cb and cr stripe from top to bottom
    "sierpinski"   Sierpinski carpet/triangle fractal
    =============  ==============================================================================

    https://ffmpeg.org/ffmpeg-filters.html#Video-Sources

    """

    url = filter_utils.compose_filter(name, *args, **kwargs)

    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url, {"f": "lavfi"})

    ffmpeg_args, reader_cfg = configure.video_io(
        ffmpeg_args,
        url,
        output_url="-",
        format="rawvideo",
    )
    dtype, shape, rate = reader_cfg[0]

    n = int(rate * duration)

    configure.merge_user_options(ffmpeg_args, "output", {"frames:v": n}, file_index=0)
    return ffmpegprocess.run(
        ffmpeg_args,
        progress=progress,
        dtype=dtype,
        shape=shape,
        capture_log=False if show_log else None,
    ).stdout


def read(url, vframes=None, stream_id=0, progress=None, show_log=None, **options):
    """Read video frames

    :param url: URL of the video file to read.
    :type url: str
    :param vframes: number of frames to read, default to None. If not set,
                    uses the timing options to determine the number of frames.
    :type vframes: int, optional
    :param stream_id: video stream id (numeric part of ``v:#`` specifier), defaults to 0.
    :type stream_id: int, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param capture_log: True to capture log messages on stderr, False to send
                    logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional

    :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
    :rtype: (`fractions.Fraction`, `numpy.ndarray`)
    """

    url, stdin, input = configure.check_url(url, False)

    args = configure.input_timing({}, url, vstream_id=stream_id, **options)

    args, reader_cfg = configure.video_io(
        args,
        url,
        stream_id,
        output_url="-",
        format="rawvideo",
        excludes=["frame_rate"],
        **options
    )
    dtype, shape, rate = reader_cfg[0]

    configure.merge_user_options(
        args, "output", {"frames:v": vframes} if vframes else {}
    )
    return (
        rate,
        ffmpegprocess.run(
            args,
            progress=progress,
            stdin=stdin,
            input=input,
            dtype=dtype,
            shape=shape,
            capture_log=False if show_log else None,
        ).stdout,
    )


def write(url, rate, data, show_log=None, progress=None, **options):
    """Write Numpy array to a video file

    :param url: URL of the video file to write.
    :type url: str
    :param rate: frame rate in frames/second
    :type rate: `float`, `int`, or `fractions.Fraction`
    :param data: video frame data 4-D array (framexrowsxcolsxcomponents)
    :type data: `numpy.ndarray`
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param capture_log: True to capture log messages on stderr, False to send
                    logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    """

    url, stdout, _ = configure.check_url(url, True)

    args = configure.input_timing(
        {},
        "-",
        vstream_id=0,
        excludes=("start", "end", "duration"),
        **{"input_frame_rate": rate, **options}
    )

    configure.codec(args, url, "v", **options)

    configure.video_io(
        args,
        utils.array_to_video_input(rate, data=data, format="rawvideo")[0],
        output_url=url,
        **options
    )

    configure.global_options(args, **options)

    if "input_options" in options:
        configure.merge_user_options(args, "input", options["input_options"])

    if "output_options" in options:
        configure.merge_user_options(args, "output", options["output_options"])

    if "global_options" in options:
        configure.merge_user_options(args, "global", options["global_options"])

    ffmpegprocess.run(
        args,
        progress=progress,
        stdout=stdout,
        input=data,
        capture_log=False if show_log else None,
    )
