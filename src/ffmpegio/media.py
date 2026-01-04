from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from collections.abc import Sequence
from ._typing import (
    Literal,
    RawStreamDef,
    ProgressCallable,
    RawDataBlob,
    Unpack,
    FFmpegUrlType,
    InputInfoDict,
    RawInputInfoDict,
    OutputInfoDict,
    RawOutputInfoDict,
    OutputPipeInfoDict,
    FFmpegOptionDict,
    DTypeString,
    ShapeTuple,
    InputPipeInfoDict,
)
from .configure import (
    FFmpegArgs,
    FFmpegOutputUrlComposite,
    FFmpegInputUrlComposite,
    FFmpegOutputUrlNoPipe,
    FFmpegNoPipeOutputOptionTuple,
    FFmpegInputUrlNoPipe,
    FFmpegNoPipeInputOptionTuple,
)

from fractions import Fraction

from . import ffmpegprocess, utils, configure, FFmpegError, plugins
from .utils import log
from .errors import FFmpegioError
from .filtergraph.abc import FilterGraphObject

__all__ = ["read", "write"]


def _runner(
    args: FFmpegArgs,
    input_info: list[InputInfoDict],
    output_info: list[OutputInfoDict],
    show_log: bool | None,
    progress: ProgressCallable | None,
    sp_kwargs: dict | None,
    overwrite: bool | None = None,
) -> tuple[
    ffmpegprocess.Popen, dict[int, InputPipeInfoDict], dict[int, OutputPipeInfoDict]
]:

    # True if there is unknown datablob info
    need_stderr = any(
        info["dst_type"] == "pipe" and info["raw_info"] is None for info in output_info
    )

    # run FFmpeg
    capture_log = True if need_stderr else None if show_log else True

    # configure named pipes
    input_pipes = output_pipes = {}
    if len(input_info):
        input_pipes, sp_kwargs = configure.assign_input_pipes(args, input_info, False)
    if len(output_info):
        output_pipes, sp_kwargs = configure.assign_output_pipes(
            args, output_info, False
        )
    stack = configure.init_named_pipes(
        input_pipes, output_pipes, input_info, output_info
    )

    def on_exit(rc):
        stack.close()

    # run the FFmpeg
    try:
        proc = ffmpegprocess.Popen(
            args,
            overwrite=overwrite,
            progress=progress,
            capture_log=capture_log,
            sp_kwargs=sp_kwargs,
            on_exit=on_exit,
        )
    except:
        # if Popen failed to start FFmpeg process, need to call the callback
        stack.close()
        raise

    # wait for the FFmpeg to finish processing
    proc.wait()

    # throw error if failed
    if proc.returncode:
        raise FFmpegError(proc.stderr, capture_log)

    return proc, input_pipes, output_pipes


def _gather_outputs(
    output_info: list[RawOutputInfoDict],
    pipe_info: dict[int, OutputPipeInfoDict],
) -> tuple[dict[str, int | Fraction], dict[str, RawDataBlob]]:

    rates = {}
    data = {}
    for i, pinfo in pipe_info.items():
        info = output_info[i]

        spec = info["user_map"]
        b = pinfo["reader"].read_all()
        dtype, shape, rate = info["raw_info"]

        data[spec] = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )
        rates[spec] = rate

    return rates, data


def read(
    *urls: *tuple[
        FFmpegInputUrlComposite
        | tuple[FFmpegInputUrlComposite, FFmpegOptionDict | None]
    ],
    streams: (
        Sequence[str]
        | Sequence[FFmpegOptionDict]
        | dict[str, FFmpegOptionDict | None]
        | None
    ) = None,
    extra_outputs: (
        Sequence[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ) = None,
    squeeze: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> tuple[dict[str, Fraction | int], dict[str, RawDataBlob]]:
    """Read video and audio data from multiple media files

    :param *urls: URLs of the media files to read or a tuple of the URL and its input option dict.
    :param streams: a list of FFmpeg output stream map options. Alternately, the list
                may consist of an FFmpeg output option dict (with a required `'map'` item)
                a dict keyed by the map option value to apply different set of
                output options to each output. If not specified (default), it
                outputs all the streams.
    :param extra_outputs: list of additional encoded output sources, defaults to
                          None. Each destination may be a url string or a pair of
                          a url string and an option dict.
    :param squeeze: False to return 4D data for video and 2D data for audio. True
                    eliminates any dimensions which only has the length of one.
     :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                        input url or '_in' to be applied to all inputs. The url-specific option gets the
                        preference (see :doc:`options` for custom options)
    :return: frame/sampling rates and raw data for each requested stream

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          `ffmpegio.video.read()` for each url.

    Specify the streams to return by `map` output option:

        map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    """

    args, input_info, output_info = configure.init_media_read(
        urls, streams, options, extra_outputs, squeeze
    )

    # run FFmpeg
    proc, input_pipes, output_pipes = _runner(
        args, input_info, output_info, show_log, progress, sp_kwargs
    )

    # gather and return output
    return _gather_outputs(output_info, output_pipes)


def write(
    urls: (
        FFmpegOutputUrlComposite
        | list[
            FFmpegOutputUrlComposite | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
        ]
    ),
    stream_types: Sequence[Literal["a", "v"]],
    *stream_args: *tuple[RawStreamDef, ...],
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
):
    """write multiple streams to a url/file

    :param url: output url
    :param stream_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
    :param stream_args: raw input stream data arguments, each input stream is either a tuple of a sample rate (audio) or frame rate (video) followed by a data blob
                         or a tuple of a data blob and a dict of input options. The option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param merge_audio_streams: True to combine all input audio streams as a single multi-channel stream. Specify a list of the input stream id's
                                (indices of `stream_types`) to combine only specified streams.
    :param merge_audio_ar: Sampling rate of the merged audio stream in samples/second, defaults to None to use the sampling rate of the first merging stream
    :param merge_audio_sample_fmt: Sample format of the merged audio stream, defaults to None to use the sample format of the first merging stream
    :param overwrite: True to overwrite if output url exists, defaults to None (auto-select)
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                      used to run the FFmpeg, defaults to None
    :param **options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                      will be applied to all input streams unless the option has been already defined in `stream_data`

    TIPS
    ----

    * All the input streams will be added to the output file by default, unless `map` option is specified
    * If the input streams are of different durations, use `shortest=ffmpegio.FLAG` option to trim all streams to the shortest.
    * Using merge_audio_streams:
      - adds a `filter_complex` global option
      - merged input streams are removed from the `map` option and replaced by the merged stream

    """

    if not isinstance(urls, list):
        urls = [urls]

    args, input_info, output_info = configure.init_media_write(
        urls, stream_types, stream_args, extra_inputs, options
    )

    # run FFmpeg
    _runner(args, input_info, output_info, show_log, progress, sp_kwargs, overwrite)

    # gather output
    data = {}
    for i, info in enumerate(output_info):
        if info["dst_type"] == "buffer":
            data[i] = info["reader"].read_all()

    return data if len(data) else None


def filter(
    expr: str | FilterGraphObject | Sequence[str | FilterGraphObject] | None,
    input_types: Sequence[Literal["a", "v"]],
    *input_args: *tuple[RawStreamDef, ...],
    extra_inputs: (
        list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    output_args: Sequence[str] | dict[str, FFmpegOptionDict | None] | None,
    extra_outputs: (
        list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ) = None,
    squeeze: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> tuple[dict[str, Fraction | int], dict[str, RawDataBlob]]:
    """write multiple streams to a url/file

    :param expr: complex filtergraph expression or a list of expressions
    :param input_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
    :param input_args: raw input stream data arguments, each input stream is either a tuple of a sample rate (audio) or frame rate (video) followed by a data blob
                         or a tuple of a data blob and a dict of input options. The option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param output_options: specific options for keyed filtergraph output pads.
    :param progress: progress callback function, defaults to None
    :param overwrite: True to overwrite if output url exists, defaults to None (auto-select)
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                      used to run the FFmpeg, defaults to None
    :param **options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                      will be applied to all input streams unless the option has been already defined in `stream_data`

    TIPS
    ----

    * Unlike `media.read()` all filtergraph outputs are always captured. The output
      options specified as keyword arguments for all outputs, and `output_options`
      argument can be used to specify additional (overriding) FFmpeg output options
      for some outputs as needed.

    """

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_filter(
        expr,
        input_types,
        input_args,
        extra_inputs,
        output_args,
        extra_outputs,
        options,
        squeeze,
    )

    if output_info is None:
        raise RuntimeError("Something went wrong in setting up filter operation...")

    # run FFmpeg
    proc, input_pipes, output_pipes = _runner(
        args, input_info, output_info, show_log, progress, sp_kwargs
    )

    # gather and return output
    return _gather_outputs(output_info, output_pipes)
