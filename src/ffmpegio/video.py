import warnings
import logging
from fractions import Fraction

from . import configure, plugins, analyze, FFmpegioError, utils
from .std_runners import run_and_return_raw, run_and_return_encoded

from ._typing import Any, ProgressCallable, RawDataBlob, FFmpegOptionDict

from .configure import (
    FFmpegInputOptionTuple,
    FFmpegInputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegNoPipeInputOptionTuple,
    FFmpegOutputUrlNoPipe,
    FFmpegNoPipeOutputOptionTuple,
)
from . import filtergraph as fgb

__all__ = ["create", "read", "write", "filter", "detect"]

logger = logging.getLogger("ffmpegio")


def create(
    expr: str | fgb.abc.FilterGraphObject,
    *args,
    squeeze: bool = True,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> tuple[Fraction | int, RawDataBlob]:
    """Create a video using a source video filter

    :param expr: source filter graph
    :param \\*args: sequential filter option arguments. Only valid for
                    a single-filter expr, and they will overwrite the
                    options set by expr.
    :param squeeze: False to return 2D data with the 2nd dimension as the audio
                    channels, defaults to True to reduce monaural data to 1D,
                    eliminating the singular audio channel dimension.
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
    :return rate: frame rate in frames/second
    :return data: video data object specified by selected `bytes_to_video` plugin hook.
                  The output shape is 4D (time x row x column x comp).
                  (since v0.12.0) With `squeeze=True` the shape dimensions with
                  length 1 are removed.

    ...seealso::
      https://ffmpeg.org/ffmpeg-filters.html#Video-Sources for available
      video source filters

    """

    url, t_, options = configure.config_input_fg(expr, args, options)

    if t_ is None and not any(
        a in options for a in ("t_in", "to_in", "t", "to", "frames:v", "vframes")
    ):
        warnings.warn(
            "neither input nor output duration specified. this function call may hang."
        )

    return read(
        url,
        squeeze=squeeze,
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
    squeeze: bool = True,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> tuple[Fraction | int, RawDataBlob]:
    """Read video frames

    :param url: URL of the video file to read or a list of URLs to be used by
                complex filtergraph. Each url may be accompanied by its own input
                options (a tuple pair of url and its option dict). These options
                supersede the input options given with keyword arguments with `'_in'`
                suffix.
    :param extra_outputs: list of additional encoded output sources, defaults to
                          None. Each destination may be a url string or a pair of
                          a url string and an option dict.
    :param squeeze: False to return 2D data with the 2nd dimension as the audio
                    channels, defaults to True to reduce monaural data to 1D,
                    eliminating the singular audio channel dimension.
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)

    :return: frame rate and video frame data, created by `bytes_to_video` plugin hook
    """

    # use user-specified map or default '0:a:0' map
    output_map = options.pop("map", "0:V:0")

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_read(
        [url] if utils.is_valid_input_url(url) else url,
        [output_map],
        options,
        extra_outputs,
        squeeze,
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
    )


def write(
    url: (
        FFmpegInputUrlComposite
        | FFmpegInputOptionTuple
        | list[FFmpegInputUrlComposite | FFmpegInputOptionTuple]
    ),
    rate_in: Fraction | int,
    data: RawDataBlob,
    *,
    extra_inputs: (
        list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    progress: ProgressCallable | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    two_pass: bool = False,
    pass1_omits: list[str] | None = None,
    pass1_extras: list[FFmpegOptionDict] | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> bytes | None:
    """Write raw video data blob

    :param url: URL of the video file to write.
    :param rate_in: frame rate in frames/second
    :param data: video frame data object, accessed by `video_info` and `video_bytes` plugin hooks
    :param progress: progress callback function, defaults to None
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :param two_pass: True to encode in 2-pass
    :param pass1_omits: list of output arguments to ignore in pass 1, defaults to None
    :param pass1_extras: list of additional output arguments to include in pass 1, defaults to None
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    """

    if utils.is_valid_output_url(url):
        url = [url]

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

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_write(
        url, ["v"], [(rate_in, data)], extra_inputs, options
    )

    return run_and_return_encoded(
        progress,
        overwrite,
        show_log,
        sp_kwargs,
        args,
        input_info,
        output_info,
        two_pass,
        pass1_omits,
        pass1_extras,
    )


def filter(
    expr: str | fgb.abc.FilterGraphObject | None,
    input_rate: Fraction | int,
    input: RawDataBlob,
    *,
    extra_inputs: (
        list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    extra_outputs: (
        list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ) = None,
    squeeze: bool = True,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
) -> tuple[Fraction | int, RawDataBlob]:
    """Filter video frames.

    :param expr: filter graph or None if implicit filtering via output options.
    :param rate: input frame rate in frames/second
    :param input: input video frame data blob, accessed by `video_info` and `video_bytes` plugin hooks
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :return: output frame rate and video frame data, created by `bytes_to_video` plugin hook

    """

    if expr and extra_inputs is None and extra_outputs is None:
        # guaranteed SISO filtering
        options["filter:v"] = expr
        options["map"] = "0:V:0"
        expr = None

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_filter(
        expr,
        ["v"],
        [(input_rate, input)],
        extra_inputs,
        None,
        extra_outputs,
        options,
        squeeze,
    )

    if output_info is None:
        raise RuntimeError("Something went wrong in setting up filter operation...")

    return run_and_return_raw(
        args, input_info, output_info, progress, show_log, sp_kwargs
    )


def detect(
    url,
    *features,
    ss=None,
    t=None,
    to=None,
    start_at_zero=False,
    time_units=None,
    progress=None,
    show_log=None,
    scene_all_scores=False,
    **options,
):
    """detect video frame features

    :param url: video file url
    :type url: str
    :param \*features: specify frame features to detect:

        ============  ===============  =========================================================
        feature       FFmpeg filter    description
        ============  ===============  =========================================================
        'scene'       `scdet`_          Detect video scene change
        'black'       `blackdetect`_    Detect video intervals that are (almost) completely black
        'blackframe'  `blackframe`_     Detect frames that are (almost) completely black
        'freeze'      `freezedetect`_   Detect frozen video
        ============  ===============  =========================================================

        defaults to include all the features
    :type \*features: tuple, a subset of ('scene', 'black', 'blackframe', 'freeze'), optional
    :param ss: start time to process, defaults to None
    :type ss: int, float, str, optional
    :param t: duration of data to process, defaults to None
    :type t: int, float, str, optional
    :param to: stop processing at this time (ignored if t is also specified), defaults to None
    :type to: int, float, str, optional
    :param start_at_zero: ignore start time, defaults to False
    :type start_at_zero: bool, optional
    :param time_units: units of detected time stamps (not for ss, t, or to), defaults to None ('seconds')
    :type time_units: 'seconds', 'frames', 'pts', optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :type show_log: bool, optional
    :param scene_all_scores: (only for 'scene' feature) True to return scores for all frames, defaults to False
    :type scene_all_scores: bool, optional
    :param \**options: FFmpeg detector filter options. For a single-feature call, the FFmpeg filter options
        of the specified feature can be specified directly as keyword arguments. For a multiple-feature call,
        options for each individual FFmpeg filter can be specified with <feature>_options dict keyword argument.
        Any other arguments are treated as a common option to all FFmpeg filters. For the available options
        for each filter, follow the link on the feature table above to the FFmpeg documentation.
    :type \**options: dict, optional
    :return: detection outcomes. A namedtuple is returned for each feature in the order specified.
        All namedtuple fields contain a list with the element specified as below:

        .. list-table::
           :header-rows: 1
           :widths: auto

           * - feature
             - named tuple field
             - element type
             - description
           * - 'scene'
             - 'time'
             - numeric
             - Timestamp of the frame
           * -
             - 'change'
             - bool
             - True if scene change detected (only present if ``scene_all_scores=True``)
           * -
             - 'score'
             - 'float'
             - Absolute difference of MAFD of current and previous frame
           * -
             - 'mafd'
             - float
             - Mean absolute frame difference. See `this commentary`_ for detailed discussion of the MAFD.
           * - 'black'
             - 'interval'
             - (numeric, numeric)
             - Interval of black frames
           * - 'blackframe'
             - 'time'
             - numeric
             - Timestamp of a black frame
           * -
             - 'pblack'
             - int
             - Percentage of black pixels
           * - 'freeze'
             - 'interval'
             - (numeric, numeric)
             - Interval of frozen frames

    :rtype: tuple of namedtuples

    Examples
    --------

    .. code-block::python

        ffmpegio.video.detect('video.mp4', 'scene')

    .. _scdet: https://ffmpeg.org/ffmpeg-filters.html#scdet-1
    .. _blackdetect: https://ffmpeg.org/ffmpeg-filters.html#blackdetect
    .. _blackframe: https://ffmpeg.org/ffmpeg-filters.html#blackframe
    .. _freezedetect: https://ffmpeg.org/ffmpeg-filters.html#freezedetect
    .. _this commentary: https://rusty.today/posts/ffmpeg-scene-change-detector

    """

    all_detectors = {
        "black": analyze.BlackDetect,
        "blackframe": analyze.BlackFrame,
        "freeze": analyze.FreezeDetect,
        "scene": analyze.ScDet,
    }

    if not len(features):
        features = [*all_detectors.keys()]

    # pop detector-specific options
    det_options = [options.pop(f"{k}_options", None) for k in features]

    # create loggers
    try:
        loggers = [all_detectors[k](**options) for k in features]
    except:
        raise ValueError(f"Unknown feature(s) specified: {features}")

    # add detector-specific options
    for l, o in zip(loggers, det_options):
        if o is not None:
            l.options.update(**o)
        if l.filter_name == "scdet":
            l.all_frames = bool(scene_all_scores)

    # exclude unspecified input options
    input_opts = {k: v for k, v in zip(("ss", "t", "to"), (ss, t, to)) if v is not None}

    # run analysis
    analyze.run(
        url,
        *loggers,
        start_at_zero=start_at_zero,
        time_units=time_units,
        progress=progress,
        show_log=show_log,
        **input_opts,
    )

    return tuple((l.output for l in loggers))
