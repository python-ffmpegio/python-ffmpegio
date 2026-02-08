import logging
from fractions import Fraction

from . import configure, utils
from . import filtergraph as fgb
from ._typing import Any, DTypeString, ProgressCallable, RawDataBlob, ShapeTuple
from .configure import (
    FFmpegInputOptionTuple,
    FFmpegInputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegNoPipeInputOptionTuple,
    FFmpegNoPipeOutputOptionTuple,
    FFmpegOutputUrlNoPipe,
)
from .errors import FFmpegioError
from .std_runners import run_and_return_encoded, run_and_return_raw

__all__ = ["create", "read", "write", "filter", "detect"]

logger = logging.getLogger("ffmpegio")


def create(
    expr: str | fgb.abc.FilterGraphObject,
    *args,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> RawDataBlob:
    """Create an image using a source video filter

    :param name: name of the source filter
    :param \\*args: sequential filter option arguments. Only valid for
                    a single-filter expr, and they will overwrite the
                    options set by expr.
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: Named filter options or FFmpeg options. Items are
                        only considered as the filter options if expr is a
                        single-filter graph, and take the precedents over
                        general FFmpeg options. Append '_in' for input
                        option names (see :doc:`options`), and '_out' for
                        output option names if they conflict with the filter
                        options.
    :return data: video data object specified by selected `bytes_to_video` plugin hook.
                  The output shape is 3D (row x column x comp) if colored/transparent.
                  or 2D (row x column) if it is a grayscale image.

    .. seealso::
        See https://ffmpeg.org/ffmpeg-filters.html#Video-Sources for
        available video source filters

    """

    url, t_, options = configure.config_input_fg(expr, args, options)

    return read(
        url,
        progress=progress,
        show_log=show_log,
        sp_kwargs=sp_kwargs,
        **options,
    )


def read(
    url: (
        FFmpegInputUrlComposite
        | FFmpegInputOptionTuple
        | list[FFmpegInputUrlComposite | FFmpegInputOptionTuple]
    ),
    *,
    extra_outputs: (
        list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ) = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> RawDataBlob:
    """Read an image file or a snapshot of a video frame

    :param url: URL of the image or video file to read.
    :param extra_outputs: list of additional encoded output sources, defaults to
                          None. Each destination may be a url string or a pair of
                          a url string and an option dict.
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :return data: video data object specified by selected `bytes_to_video` plugin hook.
                  The output shape is 3D (row x column x comp) if colored/transparent.
                  or 2D (row x column) if it is a grayscale image.

    Note on \\**options: To specify the video frame capture time, use `time`
    option which is an alias of `start` standard option.
    """

    # use user-specified map or default '0:V:0' map
    output_map = options.pop("map", "0:V:0")

    # make sure it reads only one file
    options["vframes" if "vframes" in options else "frames:v"] = 1

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_read(
        [url] if utils.is_valid_input_url(url) else url,
        [output_map],
        options,
        extra_outputs,
        True,
    )

    if output_info is None:
        raise FFmpegioError(
            "Unknown configuration error occurred. Necessary output information could not be collected."
        )
    if output_info[0]["media_type"] != "video":
        raise ValueError("Mapped stream is not a video stream.")

    return run_and_return_raw(
        args,
        input_info,
        output_info,
        progress,
        show_log,
        sp_kwargs,
    )[1]


def write(
    url: (
        FFmpegInputUrlComposite
        | FFmpegInputOptionTuple
        | list[FFmpegInputUrlComposite | FFmpegInputOptionTuple]
    ),
    data: RawDataBlob,
    *,
    extra_inputs: (
        list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    dtype: DTypeString | None = None,
    shape: ShapeTuple | None = None,
    progress: ProgressCallable | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> bytes | None:
    """Write a NumPy array to an image file.

    :param url: URL of the image file to write.
    :param data: image data, accessed by `video_info()` and `video_bytes()` plugin hooks
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    """

    # if filter_complex is not defined use '0:V:0' as default mapping
    if (
        not any(
            (o in options)
            for o in (
                "filter_complex",
                "lavfi",
                "/filter_complex",
                "/lavfi",
                "filter_complex_script",
            )
        )
        and "map" not in options
    ):
        options["map"] = "0:V:0"

    options["vframes" if "vframes" in options else "frames:v"] = 1

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_write(
        url, [{"r": 1}], extra_inputs, options, [data], [dtype], [shape]
    )

    return run_and_return_encoded(
        progress,
        overwrite,
        show_log,
        sp_kwargs,
        args,
        input_info,
        output_info,
    )


def filter(
    expr: str | fgb.abc.FilterGraphObject | None,
    input: RawDataBlob,
    *,
    extra_inputs: (
        list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    extra_outputs: (
        list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ) = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> tuple[Fraction | int, RawDataBlob]:
    """Filter image pixels.

    :param expr: SISO filter graph or None if implicit filtering via output options.
    :param input: input image data, accessed by `video_info` and `video_bytes` plugin hooks
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :return data: video data object specified by selected `bytes_to_video` plugin hook.
                  The output shape is 3D (row x column x comp) if colored/transparent.
                  or 2D (row x column) if it is a grayscale image.

    """

    if expr is not None:
        if extra_inputs is None and extra_outputs is None:
            # guaranteed SISO filtering
            options["filter:v"] = expr
            options["map"] = "0:V:0"
        else:
            options["filter_complex"] = expr

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_filter(
        [{"r": 1}], extra_inputs, None, extra_outputs, options, True, [input]
    )

    if output_info is None:
        raise RuntimeError("Something went wrong in setting up filter operation...")

    return run_and_return_raw(
        args, input_info, output_info, progress, show_log, sp_kwargs
    )[1]
