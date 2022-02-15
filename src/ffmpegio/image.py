from . import ffmpegprocess, utils, configure, FFmpegError, probe, plugins
from .utils import filter as filter_utils, log as log_utils


def _run_read(*args, shape=None, pix_fmt_in=None, s_in=None, show_log=None, **kwargs):
    """run FFmpeg and retrieve audio stream data
    :param *args ffmpegprocess.run arguments
    :type *args: tuple
    :param shape: output frame size if known, defaults to None
    :type shape: (int, int), optional
    :param pix_fmt_in: input pixel format if known but not specified in the ffmpeg arg dict, defaults to None
    :type pix_fmt_in: str, optional
    :param s_in: input frame size (wxh) if known but not specified in the ffmpeg arg dict, defaults to None
    :type s_in: str or (int, int), optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param **kwargs ffmpegprocess.run keyword arguments
    :type **kwargs: tuple
    :return: image data, created by `bytes_to_video` plugin hook
    :rtype: object
    """

    dtype, shape, _ = configure.finalize_video_read_opts(args[0], pix_fmt_in, s_in)

    if shape is None:
        configure.clear_loglevel(args[0])

        out = ffmpegprocess.run(*args, capture_log=True, **kwargs)
        if show_log:
            print(out.stderr)
        if out.returncode:
            raise FFmpegError(out.stderr)

        info = log_utils.extract_output_stream(out.stderr)
        dtype, shape = utils.get_video_format(info["pix_fmt"], info["s"])
    else:
        out = ffmpegprocess.run(
            *args,
            capture_log=None if show_log else False,
            **kwargs,
        )
        if out.returncode:
            raise FFmpegError(out.stderr)

    nbytes = utils.get_samplesize(shape, dtype)

    return plugins.get_hook().bytes_to_video(
        b=out.stdout[-nbytes:], dtype=dtype, shape=shape, squeeze=True
    )


def create(expr, *args, pix_fmt=None, vf=None, vframe=None, show_log=None, **kwargs):
    """Create an image using a source video filter

    :param name: name of the source filter
    :type name: str
    :param \\*args: filter arguments
    :type \\*args: tuple, optional
    :param pix_fmt: RGB/grayscale pixel format name, defaults to None (rgb24)
    :type pix_fmt: str, optional
    :param vf: additional video filter, defaults to None
    :type vf: FilterGraph or str, optional
    :param vframe: video frame index to capture, defaults to None (=0)
    :type vframe: int, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param \\**options: filter keyword arguments
    :type \\**options: dict, optional
    :return: image data, created by `bytes_to_video` plugin hook
    :rtype: object


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

    url, (_, s_in) = filter_utils.compose_source("video", expr, *args, **kwargs)

    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url, {"f": "lavfi"})
    outopts = configure.add_url(ffmpeg_args, "output", "-", {"f": "rawvideo"})[1][1]

    for k, v in zip(
        ("pix_fmt", "filter:v"),
        (pix_fmt or "rgb24", vf),
    ):
        if v is not None:
            outopts[k] = v

    outopts["frames:v"] = vframe if vframe else 1

    return _run_read(ffmpeg_args, s_in=s_in, show_log=show_log)


def read(url, show_log=None, **options):
    """Read an image file or a snapshot of a video frame

    :param url: URL of the image or video file to read.
    :type url: str
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional
    :return: image data, created by `bytes_to_video` plugin hook
    :rtype: object

    Note on \\**options: To specify the video frame capture time, use `time`
    option which is an alias of `start` standard option.
    """

    # get pix_fmt of the input file only if needed
    if "pix_fmt" not in options and "pix_fmt_in" not in options:
        info = probe.video_streams_basic(url, 0)[0]
        pix_fmt_in = info["pix_fmt"]
        s_in = (info["width"], info["height"])
    else:
        pix_fmt_in = s_in = None

    # get url/file stream
    url, stdin, input = configure.check_url(url, False)

    input_options = utils.pop_extra_options(options, "_in")

    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url, input_options)[1][1]
    outopts = configure.add_url(ffmpeg_args, "output", "-", options)[1][1]
    outopts["f"] = "rawvideo"
    if "frames:v" not in outopts:
        outopts["frames:v"] = 1

    return _run_read(
        ffmpeg_args,
        stdin=stdin,
        input=input,
        show_log=show_log,
        pix_fmt_in=pix_fmt_in,
        s_in=s_in,
    )


def write(url, data, overwrite=None, show_log=None, **options):
    """Write a NumPy array to an image file.

    :param url: URL of the image file to write.
    :type url: str
    :param data: image data, accessed by `video_info()` and `video_bytes()` plugin hooks
    :type data: object
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :type show_log: bool, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional
    """

    url, stdout, _ = configure.check_url(url, True)

    input_options = utils.pop_extra_options(options, "_in")

    ffmpeg_args = configure.empty()
    configure.add_url(
        ffmpeg_args,
        "input",
        *configure.array_to_video_input(1, data=data, **input_options),
    )
    outopts = configure.add_url(ffmpeg_args, "output", url, options)[1][1]
    outopts["frames:v"] = 1

    configure.build_basic_vf(ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1))

    ffmpegprocess.run(
        ffmpeg_args,
        input=plugins.get_hook().video_bytes(obj=data),
        stdout=stdout,
        overwrite=overwrite,
        capture_log=None if show_log else False,
    )


def filter(expr, input, **options):
    """Filter image pixels.

    :param expr: SISO filter graph.
    :type expr: str
    :param input: input image data, accessed by `video_info` and `video_bytes` plugin hooks
    :type input: object
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional
    :return: output sampling rate and data, created by `bytes_to_video` plugin hook
    :rtype: (int, object)

    """

    input_options = utils.pop_extra_options(options, "_in")

    ffmpeg_args = configure.empty()
    configure.add_url(
        ffmpeg_args,
        "input",
        *configure.array_to_video_input(1, data=input, **input_options),
    )
    outopts = configure.add_url(ffmpeg_args, "output", "-", options)[1][1]
    outopts["f"] = "rawvideo"
    outopts["filter:v"] = expr

    return _run_read(
        ffmpeg_args,
        input=plugins.get_hook().video_bytes(obj=input),
        show_log=True,
    )
