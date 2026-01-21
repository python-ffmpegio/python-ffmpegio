"""Audio Read/Write Module"""

from __future__ import annotations

import logging
import warnings

from . import analyze, configure, utils
from . import filtergraph as fgb
from ._typing import Any, ProgressCallable, RawDataBlob
from .configure import (
    FFmpegInputOptionTuple,
    FFmpegInputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegNoPipeInputOptionTuple,
    FFmpegNoPipeOutputOptionTuple,
    FFmpegOutputUrlNoPipe,
)
from .errors import FFmpegioError
from .filtergraph.abc import FilterGraphObject
from .std_runners import run_and_return_encoded, run_and_return_raw

logger = logging.getLogger("ffmpegio")

__all__ = ["create", "read", "write", "filter", "detect"]


def create(
    expr: str | fgb.abc.FilterGraphObject,
    *args,
    squeeze: bool = True,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
):
    """Create audio data using an audio source filter

    :param expr: name of the source filter or full filter expression
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
    :return rate: sample rate in samples/second
    :return data: audio data object specified by selected `bytes_to_audio` plugin hook.
                  (pre v0.12.0) the output shape is always 2D with the time axis in the
                  first dimension. (since v0.12.0) The shape is default to 1D if
                  data is monaural. To match the shape

    .. seealso::
        https://ffmpeg.org/ffmpeg-filters.html#Audio-Sources for available
        audio source filters

    .. warning::
        Nearly all the source filters by default continue outputting
        indefinitely. Set its  `duration` option or FFmpeg's `t` (duration)
        or `to` (end time) input/output options to make sure the function
        returns properly.

    .. note::
        output data object is determined by the selected  hook

    """

    url, t_, options = configure.config_input_fg(expr, args, options)

    if t_ is None and not any(
        a in options for a in ("t_in", "to_in", "t", "to", "frames:a", "aframes")
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
) -> tuple[int, RawDataBlob]:
    """Read audio samples.

    :param url: URL of the audio file to read or a list of URLs to be used by
                complex filtergraph. Each url may be accompanied by its own input
                options (a tuple pair of url and its option dict). These options
                supersede the input options given with keyword arguments with `'_in'`
                suffix.
    :param extra_outputs: list of additional encoded output sources, defaults to
                          None. Each destination may be url string or a pair of
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
    :return rate: sample rate in samples/second
    :return data: audio data object specified by selected `bytes_to_audio` plugin hook.
                  (pre v0.12.0) the output shape is always 2D with the time axis in the
                  first dimension. (since v0.12.0) The shape is default to 1D if
                  data is monaural. To match the shape

    .. note:: Even if :code:`start_time` option is set, all the prior samples will be read.
        The retrieved data will be truncated before returning it to the caller.
        This is to ensure the timing accuracy. As such, do not use this function
        to perform block-wise processing. Instead use the streaming solution,
        see :py:func:`open`.


    """

    # use user-specified map or default '0:a:0' map
    output_map = options.pop("map", "0:a:0")

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
    if output_info[0]["media_type"] != "audio":
        raise ValueError("Mapped stream is not an audio stream.")

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
    rate_in: int,
    data: RawDataBlob,
    *,
    extra_inputs: (
        list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    progress: ProgressCallable | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict[str, Any] | None = None,
    **options,
):
    """Write a raw audio data blob to an audio file.

    :param url: URL of the audio file to write.
    :param rate_in: The sample rate in samples/second.
    :param data: input audio data object, converted to bytes by `audio_bytes` plugin hook .
    :param progress: progress callback function, defaults to None
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    """

    # single input, put it in a list
    if utils.is_valid_output_url(url):
        url = [url]

    # if filter_complex is not defined use '0:a:0' as default mapping
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
        or "map" not in options
    ):
        options["map"] = "0:a:0"

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_write(
        url, ["a"], [(rate_in, data)], extra_inputs, options
    )

    return run_and_return_encoded(
        progress, overwrite, show_log, sp_kwargs, args, input_info, output_info
    )


def filter(
    expr: str | FilterGraphObject | None,
    input_rate: int,
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
) -> tuple[int, RawDataBlob]:
    """Filter audio samples.

    :param expr: filter graph or None if implicit filtering via output options.
    :param input_rate: Input sample rate in samples/second
    :param input: input audio data, accessed by `audio_info()` and `audio_bytes()` plugin hooks.
    :param extra_inputs: list of additional input sources, defaults to None.
                         Each source may be url string or a pair of a url string
                         and an option dict.
    :param extra_outputs: list of additional encoded output sources, defaults to
                          None. Each destination may be url string or a pair of
                          a url string and an option dict.
    :param squeeze: False to always returning 2D data with the 2nd dimension as
                    the audio channels, defaults to True to reduce monaural data
                    to 1D, eliminating the singular audio channel dimension.
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :return rate: sample rate in samples/second
    :return data: audio data object specified by selected `bytes_to_audio` plugin hook.
                  (pre v0.12.0) the output shape is always 2D with the time axis in the
                  first dimension. (since v0.12.0) The shape is default to 1D if
                  data is monaural. To match the shape

    """

    if expr and extra_inputs is None and extra_outputs is None:
        # guaranteed SISO filtering
        options["filter:a"] = expr
        options["map"] = "0:a:0"
        expr = None

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_filter(
        expr,
        ["a"],
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
    **options,
):
    """detect audio stream features

    :param url: audio file url
    :type url: str
    :param \*features: specify features to detect:

        ============  ================  =========================================================
        feature       FFmpeg filter     description
        ============  ================  =========================================================
        'silence'     `silencedetect`_  Detect silence in an audio stream
        ============  ================  =========================================================

        defaults to include all the features
    :type \*features: tuple, a subset of ('silence',), optional
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
           * - 'silence'
             - 'interval'
             - (numeric, numeric)
             - (only if mono=False) Silent interval
           * -
             - 'chX'
             - (numeric, numeric)
             - (only if mono=True) Silent interval of channel X (multiple)

    :rtype: tuple of namedtuples

    Examples
    --------

    .. code-block::python

        ffmpegio.audio.detect('audio.mp3', 'silence')

    .. _silencedetect: https://ffmpeg.org/ffmpeg-filters.html#silencedetect

    """

    all_detectors = {
        "silence": analyze.SilenceDetect,
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
