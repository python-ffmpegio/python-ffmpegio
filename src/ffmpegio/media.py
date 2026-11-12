from __future__ import annotations

import logging
from collections.abc import Sequence
from fractions import Fraction

from . import configure, ffmpegprocess, utils
from ._typing import (
    DTypeString,
    FFmpegOptionDict,
    InputInfoDict,
    InputPipeInfoDict,
    Literal,
    MediaType,
    OutputInfoDict,
    OutputPipeInfoDict,
    ProgressCallable,
    RawDataBlob,
    RawOutputInfoDict,
    ShapeTuple,
    Unpack,
)
from .configure import (
    FFmpegArgs,
    FFmpegInputOptionTuple,
    FFmpegOutputOptionTuple,
    FFmpegUrlString,
    FFmpegNoPipeInputOptionTuple,
    FFmpegNoPipeOutputOptionTuple,
    FFmpegOutputUrlComposite,
    FFmpegUrlString,
)
from .errors import FFmpegError
from .filtergraph.abc import FilterGraphObject
from .utils import RawStreamDef

logger = logging.getLogger("ffmpegio")

__all__ = ["read", "write", "filter"]


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
    # convert show_log to capture_log
    capture_log = None if show_log else True

    # configure named pipes
    input_pipes: dict[int, InputPipeInfoDict] = {}
    output_pipes: dict[int, OutputPipeInfoDict] = {}
    if len(input_info):
        input_pipes, sp_kwargs = configure.assign_input_pipes(args, input_info, False)
    if len(output_info):
        output_pipes, sp_kwargs = configure.assign_output_pipes(
            args, output_info, False
        )
    stack = configure.init_named_pipes(
        input_pipes, output_pipes, input_info, output_info, queue_size=0
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
        if "media_type" not in info:
            continue

        spec = info["user_map"]
        b = pinfo["reader"].read()
        dtype, shape, rate = info["raw_info"]

        data[spec] = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )
        rates[spec] = rate

    return rates, data


def read(
    *urls: tuple[FFmpegInputOptionTuple],
    streams: (
        Sequence[str]
        | Sequence[FFmpegOptionDict]
        | dict[str, FFmpegOptionDict | None]
        | None
    ) = None,
    extra_outputs: (
        Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
    ) = None,
    squeeze: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> tuple[dict[str, Fraction | int], dict[str, RawDataBlob]]:
    """Read multiple raw media data from multiple media files

    :param urls: URLs of the media files to read or a tuple of the URL and its input option dict.
    :type url: tuple[FFmpegInputOptionTuple]
    :param streams: a list of FFmpeg output stream map options. Alternately, the list
        may consist of an FFmpeg output option dict (with a required `'map'` item)
        a dict keyed by the map option value to apply different set of
        output options to each output. If not specified (default), it
        outputs all the streams.
    :type streams: Sequence[str] | Sequence[FFmpegOptionDict] | dict[str, FFmpegOptionDict | None] | None
    :param extra_outputs: list of additional encoded output sources, defaults to
        None. Each destination may be a url string or a pair of
        a url string and an option dict.
    :type extra_outputs: Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
    :param squeeze: False to return 4D data for video and 2D data for audio. True
        eliminates any dimensions which only has the length of one.
    :param progress: progress callback function, defaults to :code:`None` 
    :type progress: ProgressCallable | None
    :param show_log: True to show FFmpeg log messages on the console,
        defaults to :code:`None`  (no show/capture)
        Ignored if stream format must be retrieved automatically.
    :param options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
        input url or '_in' to be applied to all inputs. The url-specific option gets the
        preference (see :doc:`options` for custom options)
    :type options: :py:type:`FFmpegOptionDict <ffmpegio.typing.FFmpegOptionDict>`
    :return: a tuple containing two dicts, both keyed by requested stream specifiers

        - (dict[str, :py:class:`Fraction <fractions.Fraction>` | int]) a dict of frame/sampling rates
        - (dict[str, :py:type:`RawDataBlob <ffmpegio.typing.RawDataBlob>`]]) a dict of raw media data

    :rtype: tuple

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          :py:func:`ffmpegio.video.read()` for each url.

    Specify the streams to return by `map` output option:: python

        map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    """

    args, input_info, output_info = configure.init_media_read(
        list(urls), streams, options, extra_outputs, squeeze
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
    stream_types: Sequence[MediaType],
    *stream_args: tuple[RawStreamDef, ...],
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    stream_dtypes: list[DTypeString | None] | None = None,
    stream_shapes: list[ShapeTuple | None] | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
):
    """Write multiple raw media streams to a url/file

    :param urls: output urls
    :type urls: FFmpegOutputUrlComposite | list[FFmpegOutputUrlComposite | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]]
    :param stream_types: list/string of input stream media types, each element
        is either :code:`'a'` (audio) or :code:`'v'` (video)
    :type stream_types: Sequence[MediaType]
    :param stream_args: raw input stream data arguments, each input stream is
        either a tuple of a sample rate (audio) or frame rate
        (video) followed by a data blob, or a tuple of a data
        blob and a dict of input options. The option dict must
        include :code:`'ar'` (audio) or :code:`'r'` (video) to specify the
        rate.
    :type stream_args: tuple[RawStreamDef, ...]
    :param extra_inputs: list of additional input sources, defaults to :code:`None` .
        Each source may be url string or a pair of a url string
        and an option dict.
    :type extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None
    :param stream_dtypes: list of numpy-style data type strings of input samples
        or frames of input media streams, defaults to `None`
        (auto-detect).
    :type stream_dtypes: list[DTypeString | None]
    :param stream_shapes: list of shapes of input samples or frames of input
        media streams, defaults to `None` (auto-detect).
    :type stream_shapes: list[ShapeTuple | None]
    :param overwrite: True to overwrite if output url exists, defaults to :code:`None`  (auto-select)
    :param show_log: True to show FFmpeg log messages on the console, defaults to :code:`None`  (no show/capture)
    :param progress: progress callback function, defaults to :code:`None` 
    :type progress: ProgressCallable | None
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
        used to run the FFmpeg, defaults to :code:`None` 
    :param options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
        will be applied to all input streams unless the option has been already defined in `stream_data`
    :type options: :py:type:`FFmpegOptionDict <ffmpegio.typing.FFmpegOptionDict>`

    TIPS
    ----

    * All the input streams will be added to the output file by default, unless `map` option is specified
    * If the input streams are of different durations, use `shortest=ffmpegio.FLAG` option to trim all streams to the shortest.
    * Using merge_audio_streams:
      - adds a `filter_complex` global option
      - merged input streams are removed from the `map` option and replaced by the merged stream

    """

    input_options, input_data = utils.raw_input_options(stream_types, stream_args)

    args, input_info, output_info = configure.init_media_write(
        urls,
        input_options,
        extra_inputs,
        options,
        input_data,
        stream_dtypes,
        stream_shapes,
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
    input_types: Sequence[MediaType],
    *input_args: tuple[RawStreamDef, ...],
    output_streams: str | FFmpegOptionDict | Sequence[str | FFmpegOptionDict] | None,
    input_dtypes: list[DTypeString | None] | None = None,
    input_shapes: list[ShapeTuple | None] | None = None,
    extra_inputs: (
        list[FFmpegUrlString | FFmpegNoPipeInputOptionTuple] | None
    ) = None,
    extra_outputs: (
        list[FFmpegUrlString | FFmpegNoPipeOutputOptionTuple] | None
    ) = None,
    squeeze: bool = False,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> tuple[dict[str, Fraction | int], dict[str, RawDataBlob]]:
    """Filter multiple raw media streams

    :param expr: complex filtergraph expression or a list of expressions
    :param input_types: list/string of input stream media types, each element is
        either :code:`'a'` (audio) or :code:`'v'` (video)
    :type input_types: Sequence[MediaType]
    :param input_args: raw input stream data arguments, each input stream is
        either a tuple of a sample rate (audio) or frame rate
        (video) followed by a data blob or a tuple of a data blob
        and a dict of input options. The option dict must include
        :code:`'ar'` (audio) or :code:`'r'` (video) to specify the rate.
    :param output_streams: output stream mappings and optional per-stream options:

        - :code:`None` to map all filtergraph outputs
        - (str) output map option string
        - (dict) output ffmpeg options with the required :code:`'map'` option
        - (Sequence) a sequence of output map option string or ffmpeg option
          dict with a :code:`'map'` key.

    :type output_streams: str | FFmpegOptionDict | Sequence[str | FFmpegOptionDict] | None
    :param input_dtypes: list of numpy-style data type strings of input samples
        or frames of input media streams, defaults to `None` (auto-detect).
    :type input_dtypes: list[:py:type:`DTypeString <ffmpegio.typing.DTypeString>` | None] | None
    :param input_shapes: list of shapes of input samples or frames of input
        media streams, defaults to `None` (auto-detect).
    :type input_shapes: list[:py:type:`ShapeTuple <ffmpegio.typing.ShapeTuple>` | None] | None
    :param extra_inputs: list of additional input sources, defaults to :code:`None` .
        Each source may be url string or a pair of a url string and an option dict.
    :type extra_inputs: list[FFmpegUrlString | FFmpegNoPipeInputOptionTuple] | None
    :param extra_outputs: list of additional encoded output sources, defaults to
        None. Each destination may be a url string or a pair of
        a url string and an option dict.
    :type extra_outputs: list[FFmpegUrlString | FFmpegNoPipeOutputOptionTuple] | None
    :param squeeze: False to return 4D data for video and 2D data for audio. True
        eliminates any dimensions which only has the length of one.
    :param progress: progress callback function, defaults to :code:`None` 
    :type progress: ProgressCallable | None
    :param show_log: True to show FFmpeg log messages on the console, defaults to :code:`None`  (no show/capture)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
        used to run the FFmpeg, defaults to :code:`None` 
    :param options: FFmpeg options, append '_in' for input option names. Input options
        will be applied to all input streams unless the option has been already defined in `stream_data`
    :type options: FFmpegOptionDict
    :return: a tuple containing two dicts, both keyed by the output stream specifiers

        - (dict[str, :py:class:`Fraction <fractions.Fraction>` | int]) a dict of output frame/sampling rates
        - (dict[str, :py:type:`RawDataBlob <ffmpegio.typing.RawDataBlob>`]]) a dict of output raw media data

    :rtype: tuple

    TIPS
    ----

    * Unlike `media.read()` all filtergraph outputs are always captured. The output
      options specified as keyword arguments for all outputs, and `output_options`
      argument can be used to specify additional (overriding) FFmpeg output options
      for some outputs as needed.

    """

    if expr is not None:
        options["filter_complex"] = expr

    input_options, input_data = utils.raw_input_options(input_types, input_args)

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_filter(
        input_options,
        extra_inputs,
        output_streams,
        extra_outputs,
        options,
        squeeze,
        input_data,
        input_dtypes,
        input_shapes,
    )

    if output_info is None:
        raise RuntimeError("Something went wrong in setting up filter operation...")

    # run FFmpeg
    proc, input_pipes, output_pipes = _runner(
        args, input_info, output_info, show_log, progress, sp_kwargs
    )

    # gather and return output
    return _gather_outputs(output_info, output_pipes)
