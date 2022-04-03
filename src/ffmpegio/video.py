from . import ffmpegprocess, utils, configure, FFmpegError, probe, plugins, caps
from .utils import filter as filter_utils, log as log_utils
import logging

__all__ = ["create", "read", "write", "filter"]


def _run_read(
    *args, shape=None, pix_fmt_in=None, r_in=None, s_in=None, show_log=None, **kwargs
):
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
    :param \\**options: FFmpeg options (see :doc:`options`)
    :type \\**options: dict, optional
    :return: video data, created by `bytes_to_video` plugin hook
    :rtype: object
    """

    dtype, shape, r = configure.finalize_video_read_opts(
        args[0], pix_fmt_in, s_in, r_in
    )

    if shape is None or r is None:
        configure.clear_loglevel(args[0])

        out = ffmpegprocess.run(*args, capture_log=True, **kwargs)
        if show_log:
            print(out.stderr)
        if out.returncode:
            raise FFmpegError(out.stderr)

        info = log_utils.extract_output_stream(out.stderr)
        dtype, shape = utils.get_video_format(info["pix_fmt"], info["s"])
        r = info["r"]
    else:
        out = ffmpegprocess.run(
            *args,
            capture_log=None if show_log else False,
            **kwargs,
        )
        if out.returncode:
            raise FFmpegError(out.stderr)
    return r, plugins.get_hook().bytes_to_video(
        b=out.stdout, dtype=dtype, shape=shape, squeeze=False
    )


def create(
    expr,
    *args,
    t_in=None,
    pix_fmt=None,
    vf=None,
    progress=None,
    show_log=None,
    **kwargs,
):
    """Create a video using a source video filter

    :param name: name of the source filter
    :type name: str
    :param \\*args: filter arguments
    :type \\*args: tuple, optional
    :param t_in: duration of the video in seconds, defaults to None
    :type t_in: float, optional
    :param pix_fmt_in: input pixel format if known but not specified in the ffmpeg arg dict, defaults to None
    :type pix_fmt_in: str, optional
    :param vf: additional video filter, defaults to None
    :type vf: FilterGraph or str, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param \\**options: filter keyword arguments
    :type \\**options: dict, optional
    :return: frame rate and video data, created by `bytes_to_video` plugin hook
    :rtype: tuple[Fraction,object]

    See https://ffmpeg.org/ffmpeg-filters.html#Video-Sources for available video source filters

    """

    # =============  ==============================================================================
    # filter name    description
    # =============  ==============================================================================
    # "color"        uniformly colored frame
    # "allrgb"       frames of size 4096x4096 of all rgb colors
    # "allyuv"       frames of size 4096x4096 of all yuv colors
    # "gradients"    several gradients
    # "mandelbrot"   Mandelbrot set fractal
    # "mptestsrc"    various test patterns of the MPlayer test filter
    # "life"         life pattern based on John Conway’s life game
    # "haldclutsrc"  identity Hald CLUT
    # "testsrc"      test video pattern, showing a color pattern
    # "testsrc2"     another test video pattern, showing a color pattern
    # "rgbtestsrc"   RGB test pattern useful for detecting RGB vs BGR issues
    # "smptebars"    color bars pattern, based on the SMPTE Engineering Guideline EG 1-1990
    # "smptehdbars"  color bars pattern, based on the SMPTE RP 219-2002
    # "pal100bars"   a color bars pattern, based on EBU PAL recommendations with 100% color levels
    # "pal75bars"    a color bars pattern, based on EBU PAL recommendations with 75% color levels
    # "yuvtestsrc"   YUV test pattern. You should see a y, cb and cr stripe from top to bottom
    # "sierpinski"   Sierpinski carpet/triangle fractal
    # =============  ==============================================================================

    url, (r_in, s_in) = filter_utils.compose_source("video", expr, *args, **kwargs)

    need_t = ("mandelbrot", "life")
    if t_in is None and any((expr.startswith(f) for f in need_t)):
        raise ValueError(f"Some sources {need_t} must have t_in specified")

    ffmpeg_args = configure.empty()
    inopts = configure.add_url(ffmpeg_args, "input", url, {"f": "lavfi"})[1][1]
    outopts = configure.add_url(ffmpeg_args, "output", "-", {})[1][1]

    if t_in is not None:
        inopts["t"] = t_in

    for k, v in zip(
        ("pix_fmt", "filter:v"),
        (pix_fmt or "rgb24", vf),
    ):
        if v is not None:
            outopts[k] = v

    return _run_read(
        ffmpeg_args, progress=progress, r_in=r_in, s_in=s_in, show_log=show_log
    )


def read(url, progress=None, show_log=None, **options):
    """Read video frames

    :param url: URL of the video file to read.
    :type url: str
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional

    :return: frame rate and video frame data, created by `bytes_to_video` plugin hook
    :rtype: (fractions.Fraction, object)
    """

    pix_fmt = options.get("pix_fmt", None)

    # get pix_fmt of the input file only if needed
    pix_fmt_in = s_in = r_in = None
    if pix_fmt is None and "pix_fmt_in" not in options:
        try:
            info = probe.video_streams_basic(url, 0)[0]
            pix_fmt_in = info["pix_fmt"]
            s_in = (info["width"], info["height"])
            r_in = info["frame_rate"]
        except:
            pix_fmt_in = 'rgb24'

    input_options = utils.pop_extra_options(options, "_in")

    # get url/file stream
    url, stdin, input = configure.check_url(
        url, False, format=input_options.get("f", None)
    )

    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url, input_options)
    configure.add_url(ffmpeg_args, "output", "-", options)

    return _run_read(
        ffmpeg_args,
        stdin=stdin,
        input=input,
        progress=progress,
        show_log=show_log,
        pix_fmt_in=pix_fmt_in,
        s_in=s_in,
        r_in=r_in,
    )


def write(
    url,
    rate_in,
    data,
    progress=None,
    overwrite=None,
    show_log=None,
    two_pass=False,
    pass1_omits=None,
    pass1_extras=None,
    **options,
):
    """Write Numpy array to a video file

    :param url: URL of the video file to write.
    :type url: str
    :param rate_in: frame rate in frames/second
    :type rate_in: `float`, `int`, or `fractions.Fraction`
    :param data: video frame data object, accessed by `video_info` and `video_bytes` plugin hooks
    :type data: object
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :type show_log: bool, optional
    :param two_pass: True to encode in 2-pass
    :param pass1_omits: list of output arguments to ignore in pass 1, defaults to None
    :type pass1_omits: seq(str), optional
    :param pass1_extras: list of additional output arguments to include in pass 1, defaults to None
    :type pass1_extras: dict(int:dict(str)), optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional
    """

    url, stdout, _ = configure.check_url(url, True)

    input_options = utils.pop_extra_options(options, "_in")

    ffmpeg_args = configure.empty()
    configure.add_url(
        ffmpeg_args,
        "input",
        *configure.array_to_video_input(rate_in, data=data, **input_options),
    )
    configure.add_url(ffmpeg_args, "output", url, options)

    configure.build_basic_vf(ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1))

    kwargs = (
        {
            "pass1_omits": None if pass1_omits is None else [pass1_omits],
            "pass1_extras": None if pass1_extras is None else [pass1_extras],
        }
        if two_pass
        else {}
    )

    out = (ffmpegprocess.run_two_pass if two_pass else ffmpegprocess.run)(
        ffmpeg_args,
        input=plugins.get_hook().video_bytes(obj=data),
        stdout=stdout,
        progress=progress,
        overwrite=overwrite,
        **kwargs,
        capture_log=None if show_log else True,
    )
    if out.returncode:
        raise FFmpegError(out.stderr, show_log)


def filter(expr, rate, input, progress=None, show_log=None, **options):
    """Filter video frames.

    :param expr: SISO filter graph.
    :type expr: str
    :param rate: input frame rate in frames/second
    :type rate: `float`, `int`, or `fractions.Fraction`
    :param input: input video frame data object, accessed by `video_info` and `video_bytes` plugin hooks
    :type input: object
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :type show_log: bool, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional
    :return: output frame rate and video frame data, created by `bytes_to_video` plugin hook
    :rtype: object

    """

    input_options = utils.pop_extra_options(options, "_in")

    ffmpeg_args = configure.empty()
    configure.add_url(
        ffmpeg_args,
        "input",
        *configure.array_to_video_input(rate, data=input, **input_options),
    )
    outopts = configure.add_url(ffmpeg_args, "output", "-", options)[1][1]
    outopts["filter:v"] = expr

    return _run_read(
        ffmpeg_args,
        input=plugins.get_hook().video_bytes(obj=input),
        progress=progress,
        show_log=show_log,
    )
