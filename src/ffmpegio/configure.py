"""`configure` module

This module is used by all batch and streaming functions of `ffmpegio` to
process their input arguments and to generate FFmpeg arguments (`FFmpegArgs`)
and lists of input and output information (`InputInfoDict` and `OutputInfoDict`).

There are four primary functions for the four operation types supported by
`ffmpegio`:

========================  ================================
`init_media_read()`       encoded data to raw media data
`init_media_write()`      raw media data to encoded data
`init_media_filter()`     raw media data to raw media data
`init_media_transcode()`  encoded data to encoded data
========================  ================================

These functions call ffprobe to get raw media information best it could. However,
read calls with a non-seekable input requires to defer setting the output shape
and dtype until the necessary information is posted on the ffmpeg stderr log stream.
Likewise, filter calls with unknown input shape and dtype requires the arrival
of the first input raw data blob. In those cases, the following function must
be called after the ffmpeg operation initiates:

- `init_media_read_outputs()`
- `init_media_filter_outputs()`

The above functions do not initialize the pipes and IO threads.

- `assign_input_pipes()`
- `assign_output_pipes()`
- `init_named_pipes()`

"""

from __future__ import annotations

from functools import cache
from itertools import count
from collections import Counter

from ._typing import (
    IO,
    Literal,
    LiteralString,
    get_args,
    cast,
    Any,
    TypedDict,
    NotRequired,
    Unpack,
    Callable,
    DTypeString,
    ShapeTuple,
    RawStreamInfoTuple,
    Buffer,
    MediaType,
    FFmpegUrlType,
    FromBytesCallable,
    ToBytesCallable,
    IsEmptyCallable,
    CountDataCallable,
    RawInputInfoDict,
    RawInputInfoDict,
    EncodedInputInfoDict,
    InputInfoDict,
    InputPipeInfoDict,
    OutputInfoDict,
    RawOutputInfoDict,
    EncodedOutputInfoDict,
    OutputPipeInfoDict,
    RawStreamDef,
    RawDataBlob,
    FFmpegOptionDict,
    FilterGraphInfoDict,
)
from collections.abc import Sequence
from .utils import FFmpegInputUrlComposite, FFmpegOutputUrlComposite


from fractions import Fraction
import re, logging

logger = logging.getLogger("ffmpegio")

from io import IOBase

from namedpipe import NPopen
from contextlib import ExitStack

from . import ffmpegprocess as fp
from . import utils, probe, plugins
from . import filtergraph as fgb
from .filtergraph.abc import FilterGraphObject
from .utils.concat import FFConcat  # for typing
from ._utils import as_multi_option, is_non_str_sequence
from .utils import (
    FFmpegInputUrlComposite,
    FFmpegOutputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegOutputUrlNoPipe,
)

from .stream_spec import (
    stream_spec as compose_stream_spec,
    StreamSpecDict,
    stream_type_to_media_type,
    is_unique_stream,
    parse_map_option,
    map_option as compose_map_option,
)
from .errors import (
    FFmpegioError,
    FFmpegioNoPipeAllowed,
    FFmpegioInsufficientInputData,
    FFmpegError,
)
from .threading import ReaderThread, WriterThread, CopyFileObjThread

#################################
## module types

UrlType = Literal["input", "output"]

FFmpegInputOptionTuple = tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
"""tuple pair of FFmpeg input url compatible objects and its option dict

Supported input url objects:

- `str`
- `os.Path`
- `urllib.UrlParseResult`
- `FFConcat`
- `FilterGraphObject`
- `IO` 
- `Buffer`
"""

FFmpegOutputOptionTuple = tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
"""tuple pair of FFmpeg output url compatible objects and its option dict

Supported output url objects:

- `str`
- `IO`
- `Buffer`
"""

FFmpegNoPipeInputOptionTuple = tuple[FFmpegInputUrlNoPipe, FFmpegOptionDict]
"""tuple pair of FFmpeg input non-pipe url compatible objects and its option dict

Supported input url objects:

- `str`
- `FFConcat`
- `FilterGraphObject`
"""

FFmpegNoPipeOutputOptionTuple = tuple[FFmpegOutputUrlNoPipe, FFmpegOptionDict]
"""tuple pair of FFmpeg output non-pipe url compatible objects and its option dict
"""


raw_formats = ("rawvideo", *(formats for _, formats in utils.audio_codecs.values()))


class FFmpegArgs(TypedDict):
    """FFmpeg arguments"""

    inputs: list[FFmpegInputOptionTuple]
    # list of input definitions (pairs of url and options)
    outputs: list[FFmpegOutputOptionTuple]
    # list of output definitions (pairs of url and options)
    global_options: dict  # FFmpeg global options


InitMediaOutputsCallable = Callable[
    [
        FFmpegArgs,
        list[RawInputInfoDict | EncodedInputInfoDict],
        Any,
        list[list[RawDataBlob] | bytes],
    ],
    list[RawOutputInfoDict],
]
"""function to finalize the media output initialization

    init_media_xxx_outputs(ffmpeg_args, input_info, output_options)

    Inputs:

    args            - partial FFmpeg arguments (to be modified)
    input_info      - list of input information
    output_args     - output arguments
    deferred_inputs - list of input data 

    Outputs:

    output_info    - list of output information

    The callback may return True to cancel the FFmpeg execution.
"""


#################################
## module functions

###############################################################################
### compatible typed dicts for media initializer function keyword arguments ###
###############################################################################


class MediaReadKwsDict(TypedDict):
    input_urls: list[FFmpegInputOptionTuple]
    output_streams: list[FFmpegOptionDict] | dict[str, FFmpegOptionDict] | None
    options: FFmpegOptionDict
    squeeze: bool
    extra_outputs: list[FFmpegOutputOptionTuple] | None


class MediaWriteKwsDict(TypedDict):
    output_urls: list[FFmpegOutputOptionTuple]
    input_stream_types: list[Literal["a", "v"]]
    input_stream_args: list[tuple[RawDataBlob | None, FFmpegOptionDict]]
    options: dict[str, Any]
    input_dtypes: NotRequired[list[DTypeString | None] | None]
    input_shapes: NotRequired[list[ShapeTuple | None] | None]
    extra_inputs: list[FFmpegInputOptionTuple]


class MediaFilterKwsDict(TypedDict):
    expr: str | FilterGraphObject | list[str | FilterGraphObject] | None
    input_stream_types: list[Literal["a", "v"]]
    input_stream_args: list[tuple[RawDataBlob | None, FFmpegOptionDict]]
    output_streams: list[FFmpegOptionDict] | dict[str, FFmpegOptionDict] | None
    options: FFmpegOptionDict
    input_dtypes: NotRequired[list[DTypeString] | None]
    input_shapes: NotRequired[list[ShapeTuple] | None]
    squeeze: bool
    extra_inputs: list[FFmpegInputOptionTuple]
    extra_outputs: list[FFmpegOutputOptionTuple]


class MediaTranscoderKwsDict(TypedDict):
    input_urls: list[FFmpegInputOptionTuple]
    output_urls: list[FFmpegOutputOptionTuple]
    options: FFmpegOptionDict


FFmpegMediaKwsDict = (
    MediaReadKwsDict | MediaWriteKwsDict | MediaFilterKwsDict | MediaTranscoderKwsDict
)

####################R###
### I/O initializers ###
########################


def init_media_read(
    input_urls: Sequence[
        FFmpegInputUrlComposite
        | tuple[FFmpegInputUrlComposite, FFmpegOptionDict | None]
    ],
    output_streams: (
        Sequence[str | FFmpegOptionDict] | dict[str, FFmpegOptionDict | None] | None
    ),
    options: FFmpegOptionDict,
    extra_outputs: (
        Sequence[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ),
    squeeze: bool,
) -> tuple[FFmpegArgs, list[EncodedInputInfoDict], list[RawOutputInfoDict]]:
    """Initialize FFmpeg arguments for media read

    :param urls: URLs of the media files to read.
    :param output_streams: output stream mappings:
                - `None` to include all input streams OR all filtergraph outputs
                - a sequence of str to specify stream specifiers with file id's
                - a sequence of output option dict with `'map'` item to output-specific
                  options
                - a dict with map specifier or user keys to specify output options,
                  again to specify output-specific options. The keys will be used
                  as the keys of the raw data output, and can be different from
                  the `'map'` option so long as the `'map'` option is given in the
                  dict.
                - None to select all available streams
    :param options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                    input url or '_in' to be applied to all inputs. The url-specific option gets the
                    preference (see :doc:`options` for custom options)
    :param extra_outputs: list of additional output destinations, defaults to None.
                          Each source may be url string or a pair of a url string
                          and an option dict.
    :param squeeze: True to remove length-1 dimensions from the output shape
    :return ffmpeg_args: FFmpeg argument dict (partial)
    :return input_info: input stream information
    :return output_info: output stream information, None if outputs not initialized

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          `ffmpegio.video.read()` for each url.

    Specify the streams to return by `map` output option:

        map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
    'pix_fmt' option is not explicitly set, 'rgb24' is used.
    """

    ninputs = len(input_urls)
    if not ninputs:
        raise ValueError("At least one URL must be given.")

    if "n" in options:
        raise ValueError("Cannot have an `n` option set to output to named pipes.")

    # separate the options
    inopts_default = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = empty(utils.pop_global_options(options))
    gopts = args["global_options"]  # global options dict
    gopts["y"] = None

    # assign inputs
    input_info = process_url_inputs(args, input_urls, inopts_default)

    # assign outputs
    try:
        output_info = process_raw_outputs(
            args, input_info, output_streams, options, squeeze
        )
    except FFmpegError as e:
        raise FFmpegioInsufficientInputData(
            "Failed to retrieve input stream information."
        ) from e

    # standardize output stream options

    if extra_outputs is not None:
        output_info.extend(
            process_url_outputs(
                args,
                input_info,
                extra_outputs,
                {},
                skip_automapping=True,
                no_pipe=True,
            )
        )

    return args, input_info, output_info


def init_media_write(
    output_urls: list[
        FFmpegOutputUrlComposite | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
    ],
    input_stream_types: Sequence[Literal["a", "v"]],
    input_stream_args: Sequence[RawStreamDef],
    extra_inputs: (
        Sequence[
            FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
        ]
        | None
    ),
    options: dict[str, Any],
    input_dtypes: list[DTypeString | None] | None = None,
    input_shapes: list[ShapeTuple | None] | None = None,
) -> tuple[
    FFmpegArgs,
    list[RawInputInfoDict | EncodedInputInfoDict],
    list[EncodedOutputInfoDict],
]:
    """write multiple streams to a url/file

    :param output_url: output url
    :param input_stream_types: list/string of 'a' or 'v', specifying the input raw streams' media types
    :param input_stream_args: list of input option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                      will be applied to all input streams unless the option has been already defined in `stream_data`
    :param input_dtypes: list of numpy-style data type strings of input samples or frames
                   of input media streams, defaults to `None` (auto-detect).
    :param input_shapes: list of shapes of input samples or frames of input media streams,
                   defaults to `None` (auto-detect).
    :return ffmpeg_args: FFmpeg argument dict (partial)
    :return input_info: input stream information
    :return input_ready: Element is True if corresponding input is ready (known dtype and shape)
    :return output_info: output stream information, None if outputs not initialized
    :return output_options: output options, None if outputs already initialized

    TIPS
    ----

    * All the input streams will be added to the output file by default, unless `map` option is specified
    * If the input streams are of different durations, use `shortest=ffmpegio.FLAG` option to trim all streams to the shortest.
    * Using merge_audio_streams:
      - adds a `filter_complex` global option
      - merged input streams are removed from the `map` option and replaced by the merged stream

    """

    noutputs = len(output_urls)
    if not noutputs:
        raise FFmpegioError("At least one URL must be given.")

    # separate the options
    inopts_default = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = empty(utils.pop_global_options(options))

    # analyze and assign inputs
    input_info = process_raw_inputs(
        args,
        input_stream_types,
        input_stream_args,
        inopts_default,
        input_dtypes,
        input_shapes,
    )

    # append extra (not-piped) inputs
    if extra_inputs is not None:
        try:
            input_info.extend(process_url_inputs(args, extra_inputs, {}, no_pipe=True))
        except FFmpegioNoPipeAllowed as e:
            raise FFmpegioError("extra_inputs cannot be piped in.") from e

    # analyze and assign outputs
    output_info = process_url_outputs(args, input_info, output_urls, options)

    # if output is piped, it must have the -f option specified
    for url, opts in args["outputs"]:
        if url is None and "f" not in opts:
            raise FFmpegioError(
                'all piped encoded output stream must have its format (`"f"`) defined in its option dict'
            )

    return args, input_info, output_info


def init_media_filter(
    expr: str | FilterGraphObject | Sequence[str | FilterGraphObject] | None,
    input_stream_types: Sequence[Literal["a", "v"]],
    input_stream_args: Sequence[RawStreamDef],
    extra_inputs: Sequence[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None,
    output_streams: (
        Sequence[str | FFmpegOptionDict] | dict[str, FFmpegOptionDict | None] | None
    ),
    extra_outputs: (
        Sequence[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ),
    options: FFmpegOptionDict,
    squeeze: bool,
    input_dtypes: list[DTypeString] | None = None,
    input_shapes: list[ShapeTuple] | None = None,
) -> tuple[FFmpegArgs, list[RawInputInfoDict], list[RawOutputInfoDict]]:
    """Prepare FFmpeg arguments for media read

    :param expr: filtergraph definition(s), may be None to perform implicit filtering
                 via output options (e.g., rate or format changes)
    :param input_stream_types: list/string of 'a' or 'v', specifying the input raw streams' media types
    :param input_stream_args: list of input option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param output_streams: output stream mappings and optional per-stream options:
                - `None` to map all filtergraph outputs
                - a sequence of output option dict with `'map'` item to output-specific
                  options
                - a dict with map specifier or user keys to specify output options,
                  again to specify output-specific options. The keys will be used
                  as the keys of the raw data output, and can be different from
                  the `'map'` option so long as the `'map'` option is given in the
                  dict.
                - None to select all available streams
    :param extra_outputs: list of additional output destinations, defaults to None.
                          Each source may be url string or a pair of a url string
                          and an option dict.
    :param input_dtypes: list of numpy-style data type strings of input samples or frames
                         of input media streams, use `None` to auto-detect.
    :param input_shapes: list of shapes of input samples or frames of input media streams,
                         use `None` to auto-detect.
    :param options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                    will be applied to all input streams unless the option has been already defined in `stream_data`
    :param squeeze: True to squeeze output data blob shape
    :return ffmpeg_args: FFmpeg argument dict (partial)
    :return input_info: input stream information
    :return output_info: output stream information, None if outputs not initialized

    """

    if "n" in options:
        raise ValueError("Cannot have an `n` option set to output to named pipes.")
    if "filter_complex" in options or "lavfi" in options:
        raise ValueError(
            "Cannot have a `filter_complex` or `lavfi` option already set."
        )

    # separate the options
    inopts_default = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = empty(utils.pop_global_options(options))
    gopts = args["global_options"]  # global options dict
    gopts["y"] = None

    # complex filtergraph may not be used
    # (siso filtergraph or implicit filter like -s or -r)
    if expr is not None:
        gopts["filter_complex"] = expr

    # analyze and assign inputs
    input_info = process_raw_inputs(
        args,
        input_stream_types,
        input_stream_args,
        inopts_default,
        input_dtypes,
        input_shapes,
    )

    if extra_inputs is not None:
        try:
            input_info.extend(process_url_inputs(args, extra_inputs, {}, no_pipe=True))
        except FFmpegioNoPipeAllowed as e:
            raise FFmpegioError("extra_inputs cannot be piped in.")

    # analyze and assign outputs

    try:
        output_info = process_raw_outputs(
            args, input_info, output_streams, options, squeeze
        )
    except FFmpegError as e:
        raise FFmpegioInsufficientInputData(
            "Failed to retrieve input stream information."
        ) from e

    # if additional (encoded) outputs are specified, append them to ffmpeg args
    # and output info
    if extra_outputs is not None:
        try:
            output_info.extend(
                process_url_outputs(
                    args,
                    input_info,
                    extra_outputs,
                    {},
                    skip_automapping=True,
                    no_pipe=True,
                )
            )
        except FFmpegioNoPipeAllowed:
            raise FFmpegioError("extra_outputs cannot be piped out.")

    return args, input_info, output_info


def init_media_transcode(
    input_urls: list[FFmpegOutputUrlComposite | FFmpegInputOptionTuple],
    output_urls: list[FFmpegOutputUrlComposite | FFmpegInputOptionTuple],
    options: FFmpegOptionDict,
) -> tuple[FFmpegArgs, list[EncodedInputInfoDict], list[EncodedOutputInfoDict]]:
    """initialize media transcoder

    :param inputs: FFmpeg input options of piped inputs
    :param outputs: FFmpeg output options of piped outputs
    :param options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                    will be applied to all input streams unless the option has been already defined in `stream_data`
    :return ffmpeg_args: FFmpeg argument dict
    :return input_info: list of input stream information
    :return output_info: list of output stream information
    """

    if "n" in options:
        raise ValueError("Cannot have an `n` option set to output to named pipes.")

    # separate the options
    inopts_default = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = empty(utils.pop_global_options(options))

    input_info = process_url_inputs(args, input_urls, inopts_default)

    if not len(input_info):
        raise ValueError("At least one input must be given.")

    output_info = process_url_outputs(
        args, input_info, output_urls, options, skip_automapping=True
    )

    if not len(output_info):
        raise ValueError("At least one output must be given.")

    return args, input_info, output_info


###############################################################


def array_to_video_input(
    rate: int | Fraction | None = None,
    data: RawDataBlob | None = None,
    pipe_id: str | None = None,
    **opts: Unpack[FFmpegOptionDict],
) -> tuple[str, FFmpegOptionDict]:
    """create an stdin input with video stream

    :param rate: input frame rate in frames/second
    :param data: input video frame data, accessed with `video_info` plugin hook, defaults to None (manual config)
    :param pipe_id: named pipe path, defaults None to use stdin
    :param **opts: input options
    :return: tuple of input url and option dict
    """

    if rate is None and "r" not in opts:
        raise ValueError("rate argument must be specified if opts['r'] is not given.")

    return (
        pipe_id or "-",
        {**utils.array_to_video_options(data)[0], f"r": rate, **opts},
    )


def array_to_audio_input(
    rate: int | None = None,
    data: RawDataBlob | None = None,
    pipe_id: str | None = None,
    **opts: Unpack[FFmpegOptionDict],
):
    """create an stdin input with audio stream

    :param rate: input sample rate in samples/second
    :param data: input audio data, accessed by `audio_info` plugin hook, defaults to None (manual config)
    :param pipe_id: input named pipe id, defaults to None to use the stdin
    :return: tuple of input url and option dict
    """

    if rate is None and "ar" not in opts:
        raise ValueError("rate argument must be specified if opts['ar'] is not given.")

    return (
        pipe_id or "-",
        {**utils.array_to_audio_options(data)[0], f"ar": rate, **opts},
    )


def empty(global_options: FFmpegOptionDict | None = None) -> FFmpegArgs:
    """create empty ffmpeg arg dict

    :param global_options: global options, defaults to None
    :return: ffmpeg arg dict with empty 'inputs','outputs',and 'global_options' entries.
    """
    return {"inputs": [], "outputs": [], "global_options": global_options or {}}


def check_url(
    url: FFmpegInputUrlComposite,
    nodata: bool = True,
    nofileobj: bool = False,
    format: str | None = None,
    pipe_str: str | None = "-",
) -> tuple[
    FFmpegUrlType | FilterGraphObject | FFConcat, IOBase | None, memoryview | None
]:
    """Analyze url argument for non-url input

    :param url: url argument string or data or file or a custom class
    :param nodata: True to raise exception if url is a bytes-like object, default to True
    :param nofileobj: True to raise exception if url is a file-like object, default to False
    :param format: FFmpeg format option, default to None (unspecified)
    :param pipe_str: specify an alternate FFmpeg pipe url or None to leave it blank, default to '-'
    :return: url string, file object, and data object

    Custom Pipe Class
    -----------------

    `url` may be a class instance of which `str(url)` call yields a stdin pipe expression
    (i.e., '-' or 'pipe:' or 'pipe:0') with `url.input` returns the input data. For such `url`,
    `check_url()` returns url and data objects, accordingly.

    """

    def hasmethod(o, name):
        return hasattr(o, name) and callable(getattr(o, name))

    fileobj = None
    data = None

    if format != "lavfi":
        try:
            memoryview(url)
            data = url
            url = pipe_str
        except:
            if hasmethod(url, "fileno"):
                if nofileobj:
                    raise ValueError("File-like object cannot be specified as url.")
                fileobj = url
                url = pipe_str
            elif str(url) in ("-", "pipe:", "pipe:0"):
                try:  # for FFConcat
                    data = url.input
                except:
                    pass

        if nodata and data is not None:
            raise ValueError("Bytes-like object cannot be specified as url.")

    return url, fileobj, data


def add_url(
    args: FFmpegArgs,
    type: Literal["input", "output"],
    url: FFmpegUrlType | None,
    opts: FFmpegOptionDict | None = None,
    update: bool = False,
) -> tuple[int, FFmpegInputOptionTuple | FFmpegOutputOptionTuple]:
    """add new or modify existing url to input or output list

    :param args: ffmpeg arg dict (modified in place)
    :param type: input or output (may use None to update later)
    :param url: url of the new entry
    :param opts: FFmpeg options associated with the url, defaults to None
    :param update: True to update existing input of the same url, default to False
    :return: file index and its entry
    """

    # get current list of in/outputs
    filelist = args[f"{type}s"]
    n = len(filelist)

    # if updating, get the existing id
    file_id = (
        next((i for i in range(n) if filelist[i][0] == url), None) if update else None
    )
    if file_id is None:
        # new entry
        file_id = n
        filelist.append((url, {} if opts is None else {**opts}))
    elif opts is not None:
        # update option dict
        filelist[file_id] = (
            url,
            (
                opts
                if filelist[file_id][1] is None
                else (
                    filelist[file_id][1]
                    if opts is None
                    else {**filelist[file_id][1], **opts}
                )
            ),
        )
    return file_id, filelist[file_id]


def find_filtergraph_option(
    args: FFmpegArgs, stream: int = -1, media_type: MediaType | None = None
) -> (
    Literal[
        "filter_complex",
        "/filter_complex",
        "lavfi",
        "/lavfi",
        "filter_complex_script",
        "filter",
        "/filter",
        "af",
        "/af",
        "filter:a",
        "/filter:a",
        "vf",
        "/vf",
        "filter:v",
        "/filter:v",
    ]
    | None
):
    """True if FFmpeg arguments specify a filter graph

    :param args: FFmpeg argument dict
    :param stream: output stream index, by default -1 to check global complex filtergraphs
    :param media_type: for output stream filter, specify to check a particular
                       media type, defaults to checking both types of filters
    :return: FFmpeg option name if filter graph is specified else None
    """

    if stream < 0:  # global filtergraph
        return utils.find_filter_complex_option(args["global_options"])
    else:
        return utils.find_filter_simple_option(args["outputs"][stream], media_type)


def gather_video_read_opts(
    options: FFmpegOptionDict,
    skip_rate: bool = False,
    args: FFmpegArgs | None = None,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict] = [],
    get_fg_info: Callable[[], dict[str, FilterGraphInfoDict] | None] | None = None,
) -> tuple[RawStreamInfoTuple, FFmpegOptionDict | None]:
    """Gathering raw video read output options

    :param options: option dict for this output. To run input/fg analysis, it
                    must contain a `'map'` item.
    :param skip_rate: True to skip requiring the frame rate information, defaults
                      to False
    :param args: FFmpeg argument dict populated `inputs` and `global_options`
                 items or None to skip input & filtergraph analysis, defaults to
                 None to skip the analysis
    :param input_info: list of input information, only required if `args` is given
    :param get_fg_info: function to retrieve filtergraph output info if available.
    :return raw_info: tuple of (dtype, shape, r) where shape is a video shape
                      tuple (height, width, nb_components)
    :return additional_options: additional output options or None if `raw_info`
                                is not complete

    The output `pix_fmt` must be a raw-data compatible format (i.e., grayscales
    and RGBs, and byte-aligned alternate formats).

    If `args is None`, `options` must contain items with `s`, `pix_fmt`, and `r`
    (the latter only if `skip_rate=False`) to be successful.

    If `args` is provided, `options['map']` must be present. Also, if `options['map']`
    is a link label, `fg_info` must be provided to be successful.

    The input/fg analysis code path may raise an exception if necessary information
    is not provided.

    """

    # required options
    req_opts = ("pix_fmt", "s", "r")

    # use the output option by default
    opt_vals = [options.get(o, None) for o in req_opts]

    if opt_vals[0] is None:
        dtype = None
        ncomp = 0
    else:
        dtype, ncomp = utils.get_pixel_format(opt_vals[0])

    pix_fmt, s, r = opt_vals
    outopts = {}

    scaled_s = bool(s) and all(
        si > 0 for si in s
    )  # true if output size requires input size

    if (
        scaled_s or not all(opt_vals[:-1] if skip_rate else opt_vals)
    ) and args is not None:

        # run input analysis
        try:
            map_spec = options["map"]
        except KeyError as e:
            raise FFmpegioError('`options["map"]` is missing') from e
        map_fields = parse_map_option(map_spec, input_file_id=0)

        # get the options of the input/filtergraph output
        if linklabel := map_fields.get("linklabel", None):
            try:
                info = get_fg_info()[linklabel]
            except (AttributeError, KeyError) as e:
                raise KeyError(f"`fg_info[{linklabel}]` is missing.") from e
            try:
                pix_fmt_in = info["pix_fmt"]
                s_in = info["s"]
                r_in = info["r"]
            except KeyError as e:
                raise KeyError(
                    f'`fg_info[{linklabel}]` is missing at least one of the required video attributes ("s", "pix_fmt", "r")'
                ) from e
        else:
            # insert basic video filter if specified
            # build_basic_vf(args, False, ofile)

            ifile = map_fields["input_file_id"]

            # get input option values
            r_in, pix_fmt_in, s_in = utils.analyze_video_stream(
                map_fields["stream_specifier"],
                *args["inputs"][ifile],
                input_info[ifile],
            )

            if (vf := (options.get("vf") or options.get("filter:v"))) or scaled_s:
                # analyze output simple filter
                r_in, pix_fmt_in, s_in = utils.analyze_output_video_filter(
                    vf, r_in, pix_fmt_in, s_in, s if scaled_s else None
                )

        # pixel format must be specified
        remove_alpha = False
        if pix_fmt is None:
            # use the analyzed value, falling back to 'rgb24'
            if pix_fmt_in == "unknown":
                raise FFmpegioError(
                    "input pixel format unknown. Please specify output pix_fmt"
                )

            # deduce output pixel format from the input pixel format
            pix_fmt, ncomp, dtype, remove_alpha = utils.get_pixel_config(pix_fmt_in)
            outopts["pix_fmt"] = pix_fmt

        else:
            # make sure assigned pix_fmt is valid
            if pix_fmt_in is None:
                # shouldn't get here
                try:
                    dtype, ncomp = utils.get_pixel_format(pix_fmt)
                except Exception as e:
                    raise FFmpegioError(
                        "could not resolve output pixel format. Please specify output `'pix_fmt'` option"
                    ) from e
            else:
                remove_alpha = utils.alpha_change(pix_fmt_in, pix_fmt, -1)

        if remove_alpha:
            raise FFmpegioError(
                "The output pix_fmt does not have a transparency while its input does. "
                "Additional filtering is necessary to remove the alpha channel properly. See ffmpegio.filtergraph.presets.remove_alpha()."
            )

        if s is None:
            s = s_in

        if r is None:
            r = r_in

    # get shape tuple if resolved
    shape = (*s[::-1], ncomp) if s is not None and ncomp != 0 else None
    raw_info = (dtype, shape, r)

    # if any raw info is missing, return
    if any(v is None for v in raw_info):
        return raw_info, None

    # populate the rest of new option dict
    outopts["f"] = "rawvideo"

    return raw_info, outopts


def check_alpha_change(args, dir=None, ifile=0, ofile=0):
    # check removal of alpha channel
    inopts = args["inputs"][ifile][1]
    outopts = args["outputs"][ofile][1]
    if inopts is None or outopts is None:
        return None if dir is None else False  # indeterminable
    return utils.alpha_change(inopts.get("pix_fmt", None), outopts.get("pix_fmt", None))


def get_audio_key_opts(opts) -> RawStreamInfoTuple:
    return [opts.get(o, None) for o in ("sample_fmt", "ac", "ar")]


def gather_audio_read_opts(
    options: FFmpegOptionDict,
    skip_rate: bool = False,
    args: FFmpegArgs | None = None,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict] = [],
    get_fg_info: Callable[[], dict[str, FilterGraphInfoDict] | None] | None = None,
    default_sample_fmt: str = "dbl",
) -> tuple[RawStreamInfoTuple, FFmpegOptionDict | None]:
    """Gathering raw video read output options

    :param options: option dict for this output. To run input/fg analysis, it
                    must contain a `'map'` item.
    :param skip_rate: True to skip requiring the frame rate information, defaults
                      to False
    :param args: FFmpeg argument dict populated `inputs` and `global_options`
                 items or None to skip input & filtergraph analysis, defaults to
                 None to skip the analysis
    :param input_info: list of input information, only required if `args` is given
    :param get_fg_info: function to retrieve filtergraph output info if available.
    :param default_sample_fmt: if the input sample format is incompatible,
                               force this format, defaults to 'dbl'
    :return raw_info: audio shape tuple (nb_channels,)
    :return additional_options: additional output options or None if `raw_info`
                                is not complete

    The output `sample_fmt` must be a raw-data compatible format (i.e., grayscales
    and RGBs, and byte-aligned alternate formats).

    If `args is None`, `options` must contain items with `ac`, `sample_fmt`, and `ar`
    (the latter only if `skip_rate=False`) to be successful.

    If `args` is provided, `options['map']` must be present. Also, if `options['map']`
    is a link label, `fg_info` must be provided to be successful.

    The input/fg analysis code path may raise an exception if necessary information
    is not provided.

    """

    # required options
    req_opts = ("sample_fmt", "ac", "ar")

    # TODO - support channel_layout/ch_layout options as stronger alternative to ac

    # use the output option by default
    sample_fmt, ac, ar = [options.get(o, None) for o in req_opts]

    outopts = {}

    if (
        sample_fmt is None
        or ac is None
        or (not skip_rate and ar is None)
        and args is not None
    ):

        # run input analysis
        try:
            map_spec = options["map"]
        except KeyError as e:
            raise FFmpegioError('`options["map"]` is missing') from e
        map_fields = parse_map_option(map_spec, input_file_id=0)

        # get the options of the input/filtergraph output
        if linklabel := map_fields.get("linklabel", None):
            try:
                info = get_fg_info()[linklabel]
            except (AttributeError, KeyError) as e:
                raise KeyError(f"`fg_info[{linklabel}]` is missing.") from e
            try:
                sample_fmt_in = info["sample_fmt"]
                ac_in = info["ac"]
                ar_in = info["ar"]
            except KeyError as e:
                raise KeyError(
                    f'`fg_info[{linklabel}]` is missing at least one of the required audio attributes ("ac", "sample_fmt", "ar")'
                ) from e
        else:
            # insert basic video filter if specified
            # build_basic_vf(args, False, ofile)

            ifile = map_fields["input_file_id"]

            # get input option values
            ar_in, sample_fmt_in, ac_in = utils.analyze_audio_stream(
                map_fields["stream_specifier"],
                *args["inputs"][ifile],
                input_info[ifile],
            )

            if af := (options.get("af") or options.get("filter:a")):
                # analyze output simple filter
                sample_fmt_in, ar_in, ac_in = utils.analyze_output_audio_filter(
                    af, ar_in, sample_fmt_in, ac_in
                )

        # sample format must be specified
        if sample_fmt is None:
            sample_fmt = sample_fmt_in or default_sample_fmt

        if ac is None:
            ac = ac_in

        if ar is None:
            ar = ar_in

    # planar format is not supported, convert to interleaved format
    if sample_fmt[-1] == "p":
        sample_fmt = sample_fmt[:-1]
        outopts["sample_fmt"] = sample_fmt  # set the format to non-planar

    # sample_fmt must be given
    if sample_fmt is None:
        dtype = None
        shape = ac and (ac,)
    else:
        dtype, shape = utils.get_audio_format(sample_fmt, ac)

    # get shape tuple if resolved
    raw_info = (dtype, shape, ar)

    # if any raw info is missing, return
    if any(v is None for v in raw_info):
        return raw_info, None

    # set output format and codec
    outopts["c:a"], outopts["f"] = utils.get_audio_codec(sample_fmt)

    return raw_info, outopts


################################################################################


def get_option(ffmpeg_args, type, name, file_id=0, stream_type=None, stream_id=None):
    """get ffmpeg option value from ffmpeg args dict

    :param ffmpeg_args: ffmpeg args dict
    :type ffmpeg_args: dict
    :param type: option type: 'video', 'audio', or 'global'
    :type type: str
    :param name: option name w/out stream specifier
    :type name: str
    :param file_id: index of target file, defaults to 0
    :type file_id: int, optional
    :param stream_type: target stream type: 'v' or 'a', defaults to None
    :type stream_type: str, optional
    :param stream_id: target stream index (within specified stream type), defaults to None
    :type stream_id: int, optional
    :return: option value
    :rtype: various

    If stream is specified, several option names are looked up till one is defined. For example,
    3 entries are checked for `name`='c', `stream_type`='v', and `stream_id`=0 in this order:
    "c:v:0", "c:v", then "c". Function returns the first hit.

    """
    if ffmpeg_args is None:
        return None
    names = [name]
    if type.startswith("global"):
        opts = ffmpeg_args.get("global_options", None)
    else:
        filelists = ffmpeg_args.get(f"{type}s", None)
        if filelists is None:
            return None
        entry = filelists[file_id]
        if entry is None:
            return None
        opts = entry[1]
        if stream_type is not None:
            name += f":{stream_type}"
            names.append(name)
            if stream_id is not None:
                name += f":{stream_id}"
                names.append(name)
    if opts is None:
        return None

    v = None
    while v is None and len(names):
        name = names.pop()
        v = opts.get(name, None)

    return v


def merge_user_options(ffmpeg_args, type, user_options, file_index=None):
    if type == "global":
        type = "global_options"
        opts = ffmpeg_args.get(type, None)
        if opts is None:
            opts = ffmpeg_args[type] = {**user_options}
        else:
            ffmpeg_args[type] = {**opts, **user_options}
    else:
        type += "s"
        filelist = ffmpeg_args.get(type, None)
        if file_index is None:
            file_index = 0
        if filelist is None or len(filelist) <= file_index:
            raise Exception(f"{type} list does not have file #{file_index}")
        url, opts = ffmpeg_args[type][file_index]
        ffmpeg_args[type][file_index] = (
            url,
            {**user_options} if opts is None else {**opts, **user_options},
        )

    return ffmpeg_args


def get_video_array_format(ffmpeg_args, type, file_id=0):
    try:
        opts = ffmpeg_args[f"{type}s"][file_id][1]
    except:
        raise ValueError(f"{type} file #{file_id} is not specified")
    try:
        dtype, ncomp = utils.get_pixel_format(opts["pix_fmt"])
        shape = [*opts["s"][::-1], ncomp]
    except:
        raise ValueError(f"{type} options must specify both `s` and `pix_fmt` options")

    return shape, dtype


def move_global_options(args: FFmpegArgs) -> FFmpegArgs:
    """move global options from the output options dicts

    :param args: FFmpeg arguments
    :returns: FFmpeg arguments (the same object as the input)
    """

    from .caps import options

    _global_options = options("global", name_only=True)

    global_options = args.get("global_options", None) or {}

    # global options may be given as output options
    for _, inopts in args.get("inputs", ()):
        if inopts:
            for k in (*(k for k in inopts.keys() if k in _global_options),):
                global_options[k] = inopts.pop(k)
    for _, outopts in args.get("outputs", ()):
        if outopts:
            for k in (*(k for k in outopts.keys() if k in _global_options),):
                global_options[k] = outopts.pop(k)
    if len(global_options):
        args["global_options"] = global_options

    return args


def clear_loglevel(args: FFmpegArgs):
    """clear global loglevel option

    :param args: FFmpeg argument dict

    """
    try:
        del args["global_options"]["loglevel"]
        logger.warn("loglevel option is cleared by ffmpegio")
    except:
        pass


def finalize_avi_read_opts(args):
    """finalize multiple-input media reader setup

    :param args: FFmpeg dict
    :type args: dict
    :return: use_ya flag - True to expect grayscale+alpha pixel format rather than grayscale
    :rtype: bool

    - assumes options dict of the first output is already present
    - insert `pix_fmt='rgb24'` and `sample_fmt='sa16le'` options if these options are not assigned
    - check for the use of both 'gray16le' and 'ya8', and returns True if need to use 'ya8'
    - set f=avi and vcodec=rawvideo
    - set acodecs according to sample_fmts

    """

    # get output options, create new
    options = args["outputs"][0][1]

    # check to make sure all pixel and sample formats are supported
    gray16le = ya8 = 0
    for k in utils.find_stream_options(options, "pix_fmt"):
        v = options[k]
        if v in ("gray16le", "grayf32le"):
            gray16le += 1
        elif v in ("ya8", "ya16le"):
            ya8 += 1
    if gray16le and ya8:
        raise ValueError(
            "pix_fmts: grayscale with and without transparency cannot be mixed."
        )

    # if pix_fmt and sample_fmt not specified, set defaults
    # user can conditionally override these by stream-specific option
    if "pix_fmt" not in options:
        options["pix_fmt"] = "rgb24"
    if "sample_fmt" not in options:
        options["sample_fmt"] = "s16"

    # add output formats and codecs
    options["f"] = "avi"
    options["c:v"] = "rawvideo"

    # add audio codec
    for k in utils.find_stream_options(options, "sample_fmt"):
        options[f"c:a" + k[10:]] = utils.get_audio_codec(options[k])[0]

    return ya8 > 0


def config_input_fg(
    expr: str | FilterGraphObject, args: tuple, kwargs: dict
) -> tuple[str | fgb.Filter, float | None, dict]:
    """configure input filtergraph

    :param expr: filtergraph expression
    :param args: input argument sequence, all arguments are intended to be
                 used with the filter. Errors if expr yields a multi-filter
                 filtergraph.
    :param kwargs: input keyword argument dict. Only keys matching the
                   filter's options are consumed. The rest are returned.
    :return expr: original expression or a Filter object
    :return duration: duration in seconds if known and finite
    :return kwargs: kwargs minus the filter options.
    """
    fg = fgb.as_filtergraph_object(expr)
    dopt = None  # duration option

    if not isinstance(fg, fgb.Filter):
        # multi-filter input filtergraph, cannot take arguments
        if len(args):
            raise FFmpegioError(
                f"filtergraph input expresion cannot take ordered options."
            )
        return fg, dopt, kwargs

    # single-filter graph, can apply its options given in the arguments
    f = fg
    info = f.info
    if info.inputs is None or len(info.inputs) > 0:
        raise FFmpegioError(f"{f.name} filter is not a source filter")

    # get the full list of filter options
    opts = set()  #
    for o in info.options:
        if not dopt and o.name == "duration":
            dopt = (o.name, o.aliases, o.default)
        opts.add(o.name)
        opts.update(o.aliases)

    # split filter named option and other keyword arguments
    fargs = {i: v for i, v in enumerate(args)}
    oargs = {}
    for k, v in kwargs.items():
        (fargs if k in opts else oargs)[k] = v

    if dopt is not None:
        name, aliases, default = dopt
        val = fargs.get(name, None)
        if val is None:
            for a in aliases:
                val = fargs.get(a, None)
                if val is not None:
                    break
        if val is None:
            val = default

        dopt = utils.parse_time_duration(val)
        if dopt <= 0:
            dopt = None  # infinite

    return f.apply(fargs), dopt, oargs


def add_urls(
    ffmpeg_args: FFmpegArgs,
    url_type: UrlType,
    urls: (
        str
        | tuple[str, FFmpegOptionDict]
        | Sequence[str | tuple[str, FFmpegOptionDict]]
    ),
    *,
    update: bool = False,
) -> list[tuple[int, FFmpegInputOptionTuple | FFmpegOutputOptionTuple]]:
    """add one or more urls to the input or output list at once

    :param args: ffmpeg arg dict (modified in place)
    :param url_type: input or output
    :param urls: a sequence of urls (and optional dict of their options)
    :param opts: FFmpeg options associated with the url, defaults to None
    :param update: True to update existing input of the same url, default to False
    :return: list of file indices and their entries
    """

    def process_one(url):
        return (
            add_url(ffmpeg_args, url_type, url, update=update)
            if isinstance(url, str)
            else (
                add_url(ffmpeg_args, url_type, *url, update=update)
                if (
                    isinstance(url, tuple)
                    and len(url) == 2
                    and isinstance(url[0], str)
                    and isinstance(url[1], (dict, type(None)))
                )
                else None
            )
        )

    ret = process_one(urls)
    return [process_one(url) for url in urls] if ret is None else [ret]


def add_filtergraph(
    args: FFmpegArgs,
    filtergraph: fgb.Graph,
    map: Sequence[str] | None = None,
    automap: bool = True,
    append_filter: bool = True,
    append_map: bool = True,
    ofile: int = 0,
):
    """add a complex filtergraph to FFmpeg arguments

    :param args: FFmpeg argument dict (to be modified in place)
    :param filtergraph: Filtergraph to be added to the FFmpeg arguments
    :param map: output stream mapping, usually the output pad label, defaults to None
    :param automap: True to auto map all the output pads of the filtergraph IF `map` is None, defaults to True.
    :param append_filter: True to append `filtergraph` to the `filter_complex` global option if exists, False to replace, defaults to True
    :param append_map: True to append `map` to the `map` output option if exists, False to replace, defaults to True
    :param ofile: output file id, defaults to 0

    """

    if len(args["outputs"]) <= ofile:
        raise ValueError(
            f"The specified output #{ofile} is not defined in the FFmpegArgs dict."
        )

    if automap and map is None:
        map = [f"[{l[0]}]" for l in filtergraph.iter_output_labels()]

    # add the merging filter graph to the filter_complex argument
    gopts = args.get("global_options", None)

    if append_filter:
        complex_filters = None if gopts is None else gopts.get("filter_complex", None)
        if complex_filters is None:
            complex_filters = filtergraph
        else:
            complex_filters = as_multi_option(
                complex_filters, (str, fgb.Graph, fgb.Chain)
            )
            complex_filters.append(filtergraph)
    else:
        complex_filters = filtergraph

    if gopts is None:
        args["global_options"] = {"filter_complex": complex_filters}
    else:
        gopts["filter_complex"] = complex_filters

    if not len(map):
        # nothing to map
        return

    outopts = args["outputs"][ofile][1]
    if outopts is None:
        args["outputs"][ofile] = (args["outputs"][ofile][0], {"map": map})
    else:
        if append_map and "map" in outopts:

            existing_map = outopts["map"]

            # remove merged streams from output map & append the output stream of the filter
            map = (
                [*existing_map, *map]
                if is_non_str_sequence(existing_map)
                else [existing_map, *map]
            )

        outopts["map"] = map


class RawInputCallablesDict(TypedDict):
    data2bytes: ToBytesCallable


class RawOutputCallablesDict(TypedDict):
    bytes2data: FromBytesCallable
    data_count: CountDataCallable
    data_is_empty: IsEmptyCallable


def get_raw_output_plugin_callables(
    media_type: MediaType,
) -> RawOutputCallablesDict:
    """get three raw output plugin callbacks"""
    hook = plugins.pm.hook
    is_empty = cast(IsEmptyCallable, hook.is_empty)
    if media_type == "audio":
        return {
            "bytes2data": cast(FromBytesCallable, hook.bytes_to_audio),
            "data_count": cast(CountDataCallable, hook.audio_samples),
            "data_is_empty": is_empty,
        }

    else:
        return {
            "bytes2data": cast(FromBytesCallable, hook.bytes_to_video),
            "data_count": cast(CountDataCallable, hook.video_frames),
            "data_is_empty": is_empty,
        }


def resolve_raw_output_streams(
    stream_opts: list[FFmpegOptionDict],
    stream_names: dict[int, str],
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
) -> tuple[list[FFmpegOptionDict], list[dict]]:
    """resolve the raw output streams from given sequence of map options

    :param stream_opts: output raw stream options
    :param stream_names: user-specified names of output streams keyed by the index of `stream_opts`
    :param args: FFmpeg argument dict
    :param input_info: FFmpeg inputs' additional information, its length must match that of `args['inputs']`
    :return: list of individual output streams. Each item is a tuple of
             (stream_index, output_opts, partial_RawOutputInfoDict)

             -stream_index - index of streams
             -map_spec - final output option
             -partial_RawOutputInfoDict - to-be-completed output_info entry

    Since a map option value may yield multiple media streams (e.g., '0' or '0:v'),
    the length of returned outputs may be longer than the number of streams given.
    The user specified map value is returned in the 'user_label' field of the returned
    dicts while the

    """

    # parse all mapping option values
    input_file_id = 0 if len(input_info) == 1 else None

    inputs = args["inputs"]

    output_opts = []
    output_info = []
    for i, opts in enumerate(stream_opts):

        spec = opts["map"]
        user_map = stream_names.get(i, spec)

        try:
            opt = parse_map_option(spec, parse_stream=True, input_file_id=input_file_id)
        except ValueError:
            # incorrect spec if there is no complex filter in place
            if not utils.find_filter_complex_option(args["global_options"]):
                raise

            # test spec with possibly omitted brackets
            spec = f"[{spec}]"
            opt = parse_map_option(spec, parse_stream=True, input_file_id=input_file_id)
            opts["map"] = spec

        # get output stream information
        if "linklabel" in opt:
            # case 1: complex filtergraph requires only its outputs to be used
            #         link labels are unique, so each entry is guaranteed to be
            #         only associated with one label.

            output_opts.append(opts)
            output_info.append(
                {
                    "user_map": user_map,
                    "linklabel": opt["linklabel"],
                }
            )
        else:

            if "negative" in opt:
                raise ValueError("negative map is not supported.")

            file_index = opt["input_file_id"]
            stream_spec = opt["stream_specifier"]

            # retrieve input stream data
            if "index" in stream_spec and "stream_type" in stream_spec:
                # case 2: specific input stream with known media type
                output_opts.append(opts)
                output_info.append(
                    {
                        "user_map": user_map,
                        "media_type": stream_type_to_media_type(
                            stream_spec["stream_type"]
                        ),
                        "input_file_id": file_index,
                        "input_stream_id": -1,  # unknown and don't care
                    }
                )
            else:
                # case 3: generic stream spec, possibly resultsing in multiple output streams
                stream_data = retrieve_input_stream_ids(
                    input_info[file_index], *inputs[file_index], stream_spec=stream_spec
                )

                # append all streams
                for stream_index, media_type in stream_data:
                    output_opts.append({**opts, "map": f"{file_index}:{stream_index}"})
                    output_info.append(
                        {
                            "user_map": user_map,
                            "media_type": media_type,
                            "input_file_id": file_index,
                            "input_stream_id": stream_index,
                        },
                    )

    # resolve duplicate user_map names
    name_counts = Counter((v["user_map"] for v in output_info))

    if any(v <= 1 for v in name_counts.values()):
        return output_opts, output_info

    # create alt names in case {name}:{i} naming convention yields existing name
    # e.g.,  'v' vs. 'v:0' with 'v' resulting in multiples streams

    # first make sure alt name won't interfere with existing streams
    aliases = []
    alias_bases = {}
    for k, cnt in name_counts.items():
        if cnt <= 1:
            continue
        need_alias = False
        use_alias = None
        for i in count():
            alias = f"{k}:{i}"
            if (
                alias in name_counts
            ):  # already used, cannot be used as stream name nor alias name
                need_alias = True
                if use_alias is None:
                    continue
                else:
                    break
            elif alias not in aliases and use_alias is None:
                use_alias = alias

            if i >= cnt and (not need_alias or use_alias):
                # must count past # of stream with this user_name
                # continue counting until usable alias is found
                break

        if need_alias:
            aliases.append(use_alias)
            alias_bases[k] = use_alias

    # keep renaming counter to avoid duplicate names
    name_counter = {k: 0 for k in name_counts}

    # rename duplicate user_map's
    for info in output_info:
        user_map = info["user_map"]
        if name_counter[user_map] > 1:
            alt_base = alias_bases.get(user_map, user_map)
            info["user_map"] = f"{alt_base}:{name_counter[user_map]}"
            name_counter[user_map] += 1

    return output_opts, output_info


def format_raw_output_stream_defs(
    streams: Sequence[str | FFmpegOptionDict] | dict[str, FFmpegOptionDict] | None,
    options: FFmpegOptionDict | None,
) -> tuple[list[FFmpegOptionDict], dict[int, str]]:
    """convert user-supplied streams arguments to the standard form

    :param streams: output stream mappings:
                - `None` to include all input streams OR all filtergraph outputs
                - a sequence of str to specify stream specifiers with file id's
                - a sequence of output option dict with `'map'` item to output-specific
                  options
                - a dict with map specifier or user keys to specify output options,
                  again to specify output-specific options. The keys will be used
                  as the keys of the raw data output, and can be different from
                  the `'map'` option so long as the `'map'` option is given in the
                  dict.
                - None to select all available streams
    :param options: default output options
    :return stream_options: list of stream options
    :return stream_alias: list of pairs of stream map options and user-supplied stream labels
    """

    # depending on user's streams input, label output streams differently
    # to converge the conventions: convert streams input argument to stream_aliases and streams_ lists
    streams_: list[FFmpegOptionDict]
    stream_names: dict[int, str] = (
        {}
    )  # dict of user-specified stream name (only via dict streams input)

    if isinstance(streams, dict):  # dict[str,FFmpegOptionDict]
        # dict key is used as both stream names (labels) and map option.
        # * If FFmpegOptionDict in the dict value contains 'map' option, the key
        # would only be used as the stream name
        # * Note that if the map option is not unique the stream name will
        #   be renamed with an appended index.
        streams_ = []
        for i, (k, v) in enumerate(streams.items()):
            if "map" in v:  # user provided non-map stream name
                stream_names[i] = k
            streams_.append({**options, "map": k, **v})
    elif "map" in options:
        streams_ = [options]
    else:  # isinstance(stream,list[str|FFmpegOptionDict])
        # if an item is a str, it is the map option value
        # if FFmpegOptionDict, it must contain a 'map' option

        streams_ = [
            {**options, **({"map": v} if isinstance(v, str) else v)} for v in streams
        ]

    return streams_, stream_names


def auto_map(
    args: FFmpegArgs,
    options: FFmpegOptionDict,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
    fg_info: dict[str, FilterGraphInfoDict] | None,
) -> tuple[list[FFmpegOptionDict], list[dict[str, Any]]]:
    """list all available streams from all FFmpeg input sources

    This function complements `format_raw_output_stream_defs()`

    :param args: FFmpeg argument dict. `filter_complex` argument may be modified.
    :param options: FFmpeg output options to be applied to every output
    :param input_info: a list of input data source information
    :param fg_info: filtergraph output info if filtergraph has been pre-analyzed,
                    keyed by their linklabels or None if args does not contain any
                    complex filtergraph
    :return stream_opts: a list of FFmpeg output options
    :return stream_info: partial raw output info

    Mapping Input Streams vs. Complex Filtergraph Outputs
    -----------------------------------------------------

    If `filter_complex` global option is defined in `args`, `auto_map()` returns the mapping
    of all the output pads of the complex filtergraphs'. Otherwise, all the audio and video
    streams of the input urls are mapped.

    """

    stream_opts = []
    stream_info = []

    if fg_info is None:
        counter = {"file": None, "audio": 0, "video": 0}

        def next_map_option(i, media_type):
            if i != counter["file"]:
                counter["audio"] = counter["video"] = 0
                counter["file"] = i
            j = counter[media_type]
            counter[media_type] = j + 1
            return f"{i}:{media_type[0]}:{j}"

        # if no filtergraph, get all video & audio streams from all the input urls
        for i, ((url, opts), info) in enumerate(zip(args["inputs"], input_info)):
            for j, media_type in retrieve_input_stream_ids(info, url, opts or {}):
                spec = next_map_option(i, media_type)
                stream_opts.append({**options, "map": spec})
                stream_info.append(
                    {
                        "user_map": spec,
                        "media_type": media_type,
                        "input_file_id": i,
                        "input_stream_id": j,
                    }
                )
    else:
        # return all filtergraph outputs
        for linklabel, info in fg_info.items():
            stream_opts.append({**options, "map": linklabel})
            stream_info.append(
                {
                    "user_map": linklabel[1:-1],
                    "media_type": info["media_type"],
                    "linklabel": linklabel,
                }
            )

    return stream_opts, stream_info


def analyze_fg_outputs(args: FFmpegArgs) -> dict[str, MediaType | None]:
    """list all available output labels of the complex filtergraphs

    :param args: FFmpeg argument dict. `filter_complex` argument may be modified if present.
    :return: a map of filtergraph output labels to their media types

    Possible Complex Filtergraph Modification
    -----------------------------------------

    To enable auto-mapping, all the output pads must be labeled. Thus, if the complex filtergraphs
    in the `filter_complex` global option have any unlabeled output, they are automatically
    labeled as `outN` where N is a number starting from `0`. If a label has alraedy been assigned
    to another output pad, that label will be skipped.
    """

    gopts = args.get("global_options", None) or {}

    if "filter_complex" not in gopts:
        # no filtergraph
        return {}

    # make sure it's a list of filtergraphs
    filters_complex = utils.as_multi_option(
        gopts["filter_complex"], (str, FilterGraphObject)
    )

    # make sure all are FilterGraphObjects
    filters_complex = [fgb.as_filtergraph_object(fg) for fg in filters_complex]

    # check for unlabeled outputs and log existing output labels
    out_indices = set()
    out_labels = {}
    out_unlabeled = False
    for fg in filters_complex:
        for idx, filter, _ in fg.iter_output_pads(full_pad_index=True):
            label = fg.get_label(outpad=idx)
            if label is None:
                out_unlabeled = True
            elif m := re.match(r"out(\d+)$", label):
                out_indices.add(int(m[1]))
                out_labels[label] = (filter, idx)

    # remove all the output pads connected to an input pad of another filtergraph
    if len(filters_complex) > 1:
        for fg in filters_complex:
            for label, _ in fg.iter_input_labels():
                if label in out_labels:
                    out_labels.pop(label)

    # if there are unlabeled outputs, label them all
    if out_unlabeled:
        out_n = next(i for i in range(len(out_labels) + 1) if i not in out_labels)
        for i, fg in enumerate(filters_complex):
            new_labels = []
            for idx, filter, _ in fg.iter_output_pads(
                unlabeled_only=True, full_pad_index=True
            ):
                label = f"out{out_n}"
                out_labels[label] = (filter, idx)
                new_labels.append({"label": label, "outpad": idx})

                # next index
                while True:
                    out_n += 1
                    if out_n not in out_labels:
                        break

            for kwargs in new_labels:
                fg = fg.add_label(**kwargs)
            filters_complex[i] = fg

    # create the output map
    map = {
        f"[{label}]": filter.get_pad_media_type("output", pad_id)
        for label, (filter, pad_id) in out_labels.items()
    }

    # update the filtergraphs
    args["global_options"]["filter_complex"] = filters_complex

    return map


################################################################################


def process_url_inputs(
    args: FFmpegArgs,
    urls: Sequence[
        FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    ],
    inopts_default: FFmpegOptionDict,
    no_pipe: bool = False,
) -> list[EncodedInputInfoDict]:
    """analyze and process heterogeneous (encoded) input url argument

    :param args: FFmpeg argument dict, `args['inputs']` receives all the new inputs.
                 If input is a buffer, a fileobj, or an FFconcat, the first element
                 of the FFmpeg inputs entry is set to 'None', to be replaced by
                 a pipe expression.
    :param urls: list of input urls/data or a pair of input url and its options
    :param inopts_default: default input options
    :param no_pipe: True to raise exception if an input is piped without data buffer, defaults to False
    :return: list of input information
    """

    input_info_list = [None] * len(urls)
    for i, url in enumerate(urls):  # add inputs
        # get the option dict
        if utils.is_non_str_sequence(url, (str, FilterGraphObject, Buffer)):
            if len(url) != 2:
                raise ValueError(
                    "url-options pair input must be a tuple of the length 2."
                )
            url, opts = url
            opts = inopts_default if opts is None else {**inopts_default, **opts}
        else:
            # only URL given
            opts = inopts_default

        # check url (must be url and not fileobj)
        is_fg = isinstance(url, FilterGraphObject)
        if is_fg or ("lavfi" == opts.get("f", None) and isinstance(url, str)):
            if is_fg:
                if "f" not in opts:
                    opts["f"] = "lavfi"
                elif opts["f"] != "lavfi":
                    raise ValueError(
                        "input filtergraph must use the `'lavfi'` input format."
                    )

            input_info = {"src_type": "filtergraph"}

        elif utils.is_fileobj(url, readable=True):
            # if not url.seekable():
            #     raise FFmpegioNoPipeAllowed("Fileobj input must be seekable.")
            input_info = {"src_type": "fileobj", "fileobj": url}
            url = None
        elif utils.is_pipe(url):
            if no_pipe:
                raise FFmpegioNoPipeAllowed("No input pipe allowed.")
            input_info = {"src_type": "buffer"}
            url = None
        elif utils.is_url(url):
            input_info = {"src_type": "url"}
        elif isinstance(url, FFConcat):
            # TODO - generalize this to handle an arbitrary Muxer class
            opts["f"] = "concat"
            url0 = url.url
            if url0 in ("-", "unset"):
                input_info = {
                    "src_type": "buffer",
                    "buffer": url.compose().getvalue().encode(),
                }
                url = None
            else:
                input_info = {"src_type": "url"}
                url = url0
        else:
            try:
                buffer = memoryview(url)
            except TypeError as e:
                raise TypeError("Given input URL argument is not supported.") from e
            else:
                input_info = {"src_type": "buffer", "buffer": buffer}
                url = None

        url_opts, input_info_list[i] = (url, opts), input_info

        # leave the URL None if data needs to be piped in
        add_url(args, "input", *url_opts)

    return input_info_list


def process_raw_outputs(
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
    streams: Sequence[str] | dict[str, FFmpegOptionDict | None] | None,
    options: FFmpegOptionDict,
    squeeze: bool,
) -> list[OutputInfoDict]:
    """analyze and process piped raw outputs

    :param args: FFmpeg argument dict, A new item in`args['outputs']` is
                 appended for each piped output. Output URLs are left `None`.
    :param input_info: list of input information (same length as `args['inputs'])
    :param streams: output stream mappings:
                - `None` to include all input streams OR all filtergraph outputs
                - a sequence of str to specify stream specifiers with file id's
                - a sequence of output option dict with `'map'` item to output-specific
                  options
                - a dict with map specifier or user keys to specify output options,
                  again to specify output-specific options. The keys will be used
                  as the keys of the raw data output, and can be different from
                  the `'map'` option so long as the `'map'` option is given in the
                  dict.
                - None to select all available streams
    :param options: default output options
    :param squeeze: True to remove shape dimensions with length 1
    :return output_info: list of output information

    """

    gopts = args["global_options"]

    # on-demand complex filtergraph analysis
    @cache
    def get_fg_info() -> dict[str, FilterGraphInfoDict] | None:
        """:returns fg_info: filtergraph output info if filtergraph has been pre-analyzed,
        keyed by their linklabels, defaults to None to perform the
        filtergraph analysis internally
        """

        optname = utils.find_filter_complex_option(gopts)

        if optname is None:
            return None

        if optname in ("/filter_complex", "/lavfi", "filter_complex_script"):
            raise NotImplementedError(
                "filtergraph on a file is not yet supported. All output video streams must have `r`, `s`, and `pix_fmt` options defined."
                "Likewise, all output audio streams mjust have `ar`, `ac`, and `sample_fmt` options defined."
            )

        gopts[optname], fg_info = utils.analyze_complex_filtergraphs(
            gopts[optname], args["inputs"], input_info
        )
        return fg_info

    # resolve requested output streams
    stream_opts: list[FFmpegOptionDict]
    stream_info: list[dict[str, Any]]  # partial RawOutputInfoDict
    if (streams is None or len(streams) == 0) and "map" not in options:
        # gather all available streams keyed by their map specifier
        stream_opts, stream_info = auto_map(args, options, input_info, get_fg_info())
    else:
        stream_opts, stream_names = format_raw_output_stream_defs(streams, options)

        # expand all streams (targetting )
        stream_opts, stream_info = resolve_raw_output_streams(
            stream_opts, stream_names, args, input_info
        )

    # finalize the output configuration

    @cache
    def get_callables(media_type):
        return get_raw_output_plugin_callables(media_type)

    for opts, info in zip(stream_opts, stream_info):

        media_type = info.get("media_type", None)

        # if media_type is unknown (must be a linklabel not yet analyzed)
        if media_type is None:

            fg_info = get_fg_info()
            pad_info = fg_info[info["linklabel"]]
            info["media_type"] = media_type = pad_info["media_type"]

        # add outputs to FFmpeg arguments

        # append raw_info key to the output info dict
        gather_media_read_opts = (
            gather_audio_read_opts if media_type == "audio" else gather_video_read_opts
        )

        raw_info, more_opts = gather_media_read_opts(
            opts, False, args, input_info, get_fg_info
        )

        if more_opts is None:
            raise FFmpegioError(
                f'failed to retrieve raw data information for the stream "{info["user_map"]}"'
            )

        info["dst_type"] = "buffer"
        info["raw_info"] = raw_info
        info["item_size"] = utils.get_samplesize(*raw_info[1::-1])

        info["squeeze"] = squeeze
        info.update(get_callables(info["media_type"]))

        # finalize each output streams and identify the output formats
        add_url(args, "output", None, {**opts, **more_opts})

    return stream_info


def process_raw_inputs(
    args: FFmpegArgs,
    stream_types: Sequence[Literal["a", "v"]],
    stream_args: Sequence[RawStreamDef],
    inopts_default: FFmpegOptionDict,
    dtypes: list[DTypeString | None] | None = None,
    shapes: list[ShapeTuple | None] | None = None,
) -> list[RawInputInfoDict]:
    """configure input raw media streams

    :param args: _description_
    :param stream_types: _description_
    :param stream_args: _description_
    :param inopts_default: _description_
    :param dtypes: _description_, defaults to None
    :param shapes: _description_, defaults to None
    :return: a list of dict containing the provided info
    """
    input_info: list[RawInputInfoDict] = []
    if dtypes is None:
        dtypes = [None] * len(stream_types)
    if shapes is None:
        shapes = [None] * len(stream_types)

    @cache
    def get_callables(media_type: MediaType) -> RawInputCallablesDict:
        hook = plugins.pm.hook
        return (
            {"data2bytes": cast(ToBytesCallable, hook.audio_bytes)}
            if media_type == "audio"
            else {"data2bytes": cast(ToBytesCallable, hook.video_bytes)}
        )

    for i, (mtype, arg, dtype, shape) in enumerate(
        zip(stream_types, stream_args, dtypes, shapes)
    ):
        ropt = {"v": "r", "a": "ar"}.get(mtype, None)  # rate option
        try:
            a1, a2 = arg
            if isinstance(a1, (int, float, Fraction)):
                data = a2
                opts = {ropt: a1}
                if ropt is None:
                    raise FFmpegioError(
                        "stream_type not specified, cannot resolve the `rate` input."
                    )
            else:
                assert isinstance(a2, dict)
                data, opts = a1, a2
                if ropt is None:  # unknown
                    if "ar" in opts:
                        mtype = "a"
                        ropt = "ar"
                    elif "r" in opts:
                        mtype = "v"
                        ropt = "r"
                    else:
                        raise FFmpegioError("unknown input stream media type")

        except FFmpegioError:
            raise
        except Exception as e:
            raise ValueError(
                f"""Invalid raw stream definition: {arg}.\nEach item of `stream_args` must be a two-element tuple: 
                    - a rate (numeric) and a data_blob
                    - a data_blob and a dict of options
                """
            ) from e

        opts = {**inopts_default, **opts}
        more_opts = None
        raw_info = None
        if mtype == "a":  # audio
            media_type = "audio"
            opts[ropt] = round(opts[ropt])  # force int sampling rate
            if data is not None:
                more_opts, raw_info = utils.array_to_audio_options(data)
                data = plugins.get_hook().audio_bytes(obj=data)

            elif dtypes and shapes and shapes[i] is not None and dtypes[i] is not None:
                raw_info = (shapes[i], dtypes[i])
                sample_fmt, ac = utils.guess_audio_format(shapes[i], dtypes[i])
                acodec, f = utils.get_audio_codec(sample_fmt)
                more_opts = {"sample_fmt": sample_fmt, "ac": ac, "c:a": acodec, "f": f}

            raw_info = (*raw_info, opts["ar"]) if raw_info else (None, None, opts["ar"])

        else:  # video
            media_type = "video"
            if data is not None:
                more_opts, raw_info = utils.array_to_video_options(data)
                data = plugins.get_hook().video_bytes(obj=data)
            elif dtype and shape:
                raw_info = shape, dtype
                pix_fmt, s = utils.guess_video_format(*raw_info)
                more_opts = {
                    "f": "rawvideo",
                    "c:v": "rawvideo",
                    "pix_fmt": pix_fmt,
                    "s": s,
                }

        if raw_info is None:
            raise FFmpegioInsufficientInputData(
                "Failed to resolve raw input data format."
            )

        if more_opts is not None:
            opts.update(more_opts)

        info = {
            "src_type": "buffer",
            "media_type": media_type,
            "raw_info": (*raw_info, opts[ropt]),
            "item_size": utils.get_samplesize(*raw_info[1::-1]),
            **get_callables(media_type),
        }

        if data is not None:
            info["buffer"] = data
        add_url(args, "input", None, opts)
        input_info.append(info)

    return input_info


def update_raw_input(
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict],
    stream_id: int,
    data: RawDataBlob,
):
    """update raw input stream from the data blob

    :param args: FFmpeg arguments to be modified
    :param input_info: FFmpeg input information
    :param stream_id: index of the input stream to be updated
    :param data: input data blob

    * updates `args['inputs'][stream_id][1]` dict
    * updates `raw_info` field of ``input_info[stream_id]` dict

    """

    opts = args["inputs"][stream_id][1]
    info = input_info[stream_id]
    is_audio = info["media_type"] == "audio"
    rate = opts["ar" if is_audio else "r"]
    more_opts, raw_info = (
        utils.array_to_audio_options(data)
        if is_audio
        else utils.array_to_video_options(data)
    )

    opts.update(more_opts)
    info["raw_info"] = (*raw_info[::-1], rate)  # dtype, shape, rate


def process_url_outputs(
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
    urls: list[
        FFmpegOutputUrlComposite | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
    ],
    options: FFmpegOptionDict,
    skip_automapping: bool = False,
    no_pipe: bool = False,
) -> list[EncodedOutputInfoDict]:
    """analyze and process url outputs

    :param args: FFmpeg argument dict, A new item in`args['outputs']` is
                 appended for each piped output. Output URLs are left `None`.
    :param input_info: list of input information (same length as `args['inputs'])
    :param urls: output file names and optionally with file-specific options
    :param options: default output options. If `"map"` option is given, it is appended
                    to the per-file `"map"` option in `streams` argument
    :param skip_automapping: True to skip automapping, uses the default mapping,
                             defaults to False
    :param no_pipe: True to raise exception if output is piped without data buffer,
                    defaults to False
    :return output_info: list of output information
    """

    missing_map = False
    output_info_list = [None] * len(urls)
    for i, url in enumerate(urls):  # add inputs
        # get the option dict
        if utils.is_non_str_sequence(url, (str, FilterGraphObject, Buffer)):
            if len(url) != 2:
                raise ValueError(
                    "url-options pair input must be a tuple of the length 2."
                )
            url, opts = url
            opts = {**options} if opts is None else {**options, **opts}
        else:
            # only URL given
            opts = {**options}

        # check url (must be url and not fileobj)
        if utils.is_fileobj(url, writable=True):
            output_info = {"dst_type": "fileobj", "fileobj": url}
            url = None
        elif utils.is_pipe(url):
            if no_pipe:
                raise FFmpegioNoPipeAllowed("No output pipe allowed.")
            # convert to buffer
            output_info = {"dst_type": "buffer"}
            url = None
        elif utils.is_url(url):
            output_info = {"dst_type": "url"}
        else:
            raise TypeError("Unknown output {url}.")

        url_opts, output_info_list[i] = (url, opts), output_info

        # leave the URL None if data needs to be piped in
        add_url(args, "output", *url_opts)

        if "map" not in opts:
            missing_map = True

    if missing_map and not skip_automapping:

        # some output file is missing `map` option
        # add all input streams or all complex filter outputs

        fgname = find_filtergraph_option(args)
        if fgname is None:
            out_opts, _ = auto_map(args, options, input_info, None)
            map_opts = [o["map"] for o in out_opts]
        else:
            # get filtergraph
            fg = fgb.as_filtergraph(args["global_options"][fgname])
            map_opts = [label for label in fg.iter_output_labels()]
        # add outputs to FFmpeg arguments
        for _, opts in args["outputs"]:
            if "map" not in opts:
                opts["map"] = map_opts

    return output_info_list


def assign_input_url(args: FFmpegArgs, ifile: int, url: str):
    """assign a new url to an FFmpeg input

    :param args: FFmpeg arguments (args['inputs'][ifile] to be modified)
    :param ifile: file index
    :param url: new url
    """
    args["inputs"][ifile] = (url, args["inputs"][ifile][1])


def assign_output_url(args: FFmpegArgs, ofile: int, url: str):
    """assign a new url to an FFmpeg output

    :param args: FFmpeg arguments (args['outputs'][ofile] to be modified)
    :param ofile: file index
    :param url: new url
    """
    args["outputs"][ofile] = (url, args["outputs"][ofile][1])


def retrieve_input_stream_ids(
    info: RawInputInfoDict | EncodedInputInfoDict,
    url: FFmpegUrlType | FilterGraphObject | None,
    opts: FFmpegOptionDict,
    stream_spec: str | StreamSpecDict | None = None,
) -> list[tuple[int, MediaType]]:
    """Retrieve ids and media types of streams in an input source

    Note: The stream ids are unique ids among all streams in a container.

    :param info: input file source information
    :param url: URL or local file path of the input media file/device. None if data is provided via pipe
                and data is in the `info` argument
    :param opts: FFmpeg input options
    :param stream_spec: Specify streams to return
    :return: A list of stream indices and media types of the input streams. If
             the stream_spec is uniquely specified and media type is known, the
             index is not resolved. Maybe empty if failed to probe the media
             (e.g., data inaccessible or in an ffprobe incompatible format, e.g.,
             ffconcat)
    """

    # check raw formats first
    if info["src_type"] == "buffer" and "buffer" not in info:
        # raw input format, single-stream
        return [[0, info["media_type"]]]

    # file/network input - process only if seekable
    # get ffprobe subprocess keywords
    url, sp_kwargs, exit_fcn = utils.set_sp_kwargs_stdin(url, info)
    if sp_kwargs is None:
        # something failed (warning logged)
        return []

    def get_spec(info, opts):
        # run ffprobe
        return probe.streams_basic(
            url,
            f=opts.get("f", None),
            sp_kwargs=sp_kwargs,
            stream_spec=(
                compose_stream_spec(**stream_spec)
                if isinstance(stream_spec, dict)
                else stream_spec
            ),
        )

    # get the stream list if ffprobe can
    try:
        stream_ids = [
            (info["index"], info["codec_type"])
            for info in get_spec(info, opts)
            if info["codec_type"] in get_args(MediaType)
        ]
    except:
        # if failed, return empty
        logger.warning("ffprobe failed.")
        stream_ids = []
    finally:
        # clean-up
        exit_fcn()
    return stream_ids


########################################


def assign_output_pipes(
    args: FFmpegArgs,
    output_info: list[OutputInfoDict],
    use_std_pipes: bool = False,
) -> tuple[dict[int, OutputPipeInfoDict], dict]:
    """initialize pipes for write operations with FFmpeg

    :param args: FFmpeg option arguments (modified)
    :param output_info: FFmpeg output information, its length matches that of `args['outputs']` (modified)
    :param use_std_pipes: True to assign the first piped output to stdout
    :param sp_kwargs: the subprocess.Popen keyword arguments for stdout pipe
    :returns pipe_info: output named pipes and their writer threads keyed by output_info index
    :returns sp_kwargs: subprocess keywords with `stdout` if `use_std_pipes=True`
                        and there is at least one piped output
    """

    pipe_info = {}
    sp_kwargs = {}

    if output_info is None:
        return sp_kwargs, sp_kwargs

    # configure output pipes
    use_stdout = False
    has_pipeout = False
    pipe_info = {}

    for i, (info, arg) in enumerate(zip(output_info, args["outputs"])):

        if arg[0]:
            # url already configured
            continue

        has_pipeout = True
        if use_std_pipes and not use_stdout:
            use_stdout = True
            pipe_path = "pipe:1"

            dst_type = info["dst_type"]
            if dst_type == "fileobj":
                assert "fileobj" in info
                sp_kwargs["stdout"] = info["fileobj"]
            elif dst_type == "buffer":
                sp_kwargs["stdout"] = fp.PIPE
                pipe_info[i] = {"pipe": "stdout"}
        else:
            # if fileobj or buffer output, use pipe
            pipe = NPopen("r", bufsize=0)
            pipe_path = pipe.path
            pipe_info[i] = {"pipe": pipe}
        assign_output_url(args, i, pipe_path)

    if has_pipeout:
        # if any output is piped, must run in the overwrite mode
        args["global_options"].pop("n", None)
        args["global_options"]["y"] = None

    return pipe_info, sp_kwargs


def assign_input_pipes(
    args: FFmpegArgs,
    input_info: list[InputInfoDict],
    use_std_pipes: bool = False,
    set_sp_kwargs_input: bool = False,
) -> tuple[dict[int, InputPipeInfoDict], dict]:
    """initialize named pipes for write operations with FFmpeg

    :param args: FFmpeg option arguments (modified)
    :param input_info: FFmpeg input information, its length matches that of `args['inputs']` (modified)
    :param use_std_pipes: True to assign the first piped output to stdout
    :param set_sp_kwargs_input: True to assign 'input' instead of 'stdin' for sp_kwargs
    :returns pipe_info: input pipe information keyed by the indices of the
                        `input_info` entries with named pipe
    :returns sp_kwargs: Specify the subprocess.Popen keyword arguments for stdin related arguments

    """

    pipe_info = {}
    sp_kwargs = {}

    if input_info is None:
        return pipe_info, sp_kwargs

    # configure input pipes
    use_stdin = False

    # configure input pipes (if needed)
    for i, (info, arg) in enumerate(zip(input_info, args["inputs"])):

        if arg[0]:
            # url already configured
            continue

        if use_std_pipes and not use_stdin:
            use_stdin = True
            pipe_path = "pipe:0"

            src_type = info["src_type"]
            if src_type == "fileobj":
                assert "fileobj" in info
                sp_kwargs["stdin"] = info["fileobj"]
            elif src_type == "buffer":
                if set_sp_kwargs_input and "buffer" in info:
                    # given data to send to subprocess
                    sp_kwargs["input"] = info["buffer"]
                else:
                    sp_kwargs["stdin"] = fp.PIPE
                pipe_info[i] = {"pipe": "stdin"}
        else:
            pipe = NPopen("w", bufsize=0)
            pipe_path = pipe.path
            pipe_info[i] = {"pipe": pipe}
        assign_input_url(args, i, pipe_path)

    return pipe_info, sp_kwargs


def init_named_pipes(
    inpipe_info: dict[int, InputPipeInfoDict],
    outpipe_info: dict[int, OutputPipeInfoDict],
    input_info: list[InputInfoDict],
    output_info: list[OutputInfoDict],
    update_rate: int | Fraction | None = None,
    blocksize: int | None = None,
    queue_size: int | None = None,
    timeout: float | None = None,
    stack: ExitStack | None = None,
) -> ExitStack:
    """initialize named pipes for read & write operations with FFmpeg

    :param args: FFmpeg option arguments (modified)
    :param input_info: FFmpeg input information, its length matches that of `args['inputs']`
    :param output_info: FFmpeg output information, its length matches that of `args['outputs']` (modified)
    :param update_rate: target rate at which queue transactions will occur for raw data output,
                        defaults to None (1 video frame or 1024 audio sample at a time)
    :param blocksize: encoded data output block size in bytes, defaults to None (2**20 bytes)
    :param stack: ExitStack context manager object to handle __exit__() of NOpen and Thread objects
    :returns: a list of indices of the FFmpeg outputs that are raw data streams

    In addition to the retured list, this function modifies the dicts in its arguements.

    - The named pipe paths are assigned to the URLs of FFmpeg outputs (`args['outputs'][][0]`)
    - The reader threads for FFmpeg outputs that are written to buffers (i.e.,
      `output_info[]['dst_type']=='buffer'`) are saved as `output_info[]['reader']`
      so the reader object can be used to retrieve the data.


    if any output is a piped, overwrite flag (-y) is automatically inserted
    """

    if stack is None:
        stack = ExitStack()
    wr_kws = {"queuesize": queue_size, "timeout": timeout} if queue_size else {}

    # configure output pipes
    for i, pinfo in outpipe_info.items():
        info = output_info[i]

        pipe = pinfo["pipe"]

        if pipe == "stdout":
            continue

        stack.enter_context(pipe)

        dst_type = info["dst_type"]
        if dst_type == "fileobj":
            assert "fileobj" in info
            reader = CopyFileObjThread(pipe, info["fileobj"])
        else:
            assert dst_type == "buffer"
            kws = {**wr_kws}
            if "raw_info" in info:
                if update_rate is not None:
                    # set the number of frames/samples to enqueue at a time
                    kws["nmin"] = round(rate / update_rate) or 1
            else:
                # assume encoded output
                kws["nmin"] = blocksize or 2**16
            reader = ReaderThread(pipe, **kws)

        pinfo["reader"] = reader
        stack.enter_context(reader)  # starts thread & wait for pipe connection

    # configure input pipes
    for i, pinfo in inpipe_info.items():
        info = input_info[i]

        pipe = pinfo["pipe"]
        if pipe == "stdin":
            continue

        stack.enter_context(pipe)

        src_type = info["src_type"]
        if src_type == "fileobj":
            assert "fileobj" in info
            writer = CopyFileObjThread(info["fileobj"], pipe, auto_close=True)
            # starts thread & wait for pipe connection
        else:
            assert src_type == "buffer"
            writer = WriterThread(pipe, **wr_kws)
            # starts thread & wait for pipe connection
            if "buffer" in info:
                # data buffer given, feed the data and terminate
                writer.write(info["buffer"])
                writer.write(None)  # close the writer immediately
            else:
                # if no data given, provide the access to the writer
                pinfo["writer"] = writer
        stack.enter_context(writer)

    return stack


class StdWriter:
    def __init__(self, proc: fp.Popen) -> None:
        self._proc = proc

    def write(self, data: bytes | None):
        if data is None:
            self._proc.stdin.flush()
            self._proc.stdin.close()
        else:
            self._proc.stdin.write(data)


class StdReader:
    def __init__(self, proc: fp.Popen) -> None:
        self._proc = proc

    def read(self, n: int = -1) -> bytes:
        return self._proc.stdout.read(n)


def init_std_pipes(
    input_pipes: dict[int, InputPipeInfoDict],
    output_pipes: dict[int, OutputPipeInfoDict],
    proc: fp.Popen,
):

    stdin = next((st for st, p in input_pipes.items() if p["pipe"] == "stdin"), None)
    if stdin is not None:
        input_pipes[stdin]["writer"] = StdWriter(proc)

    stdout = next((st for st, p in output_pipes.items() if p["pipe"] == "stdout"), None)
    if stdout is not None:
        output_pipes[stdout]["reader"] = StdReader(proc)


def find_primary_output_index(
    # output_pipes: dict[int, OutputPipeInfoDict],
    output_info: list[OutputInfoDict],
    primary_output: int | str | None = None,
) -> int | None:
    """find index of the primary raw media output stream

    :param output_pipes: output pipe information dicts, keyed by output stream index
    :param output_info: output stream information list
    :param primary_output: primary output index or label, defaults to the first
                           output media stream
    :return: primary output index or None if not found
    """

    if primary_output is None:
        # use first raw stream
        return next(
            (i for i, info in enumerate(output_info) if "buffer" in info["dst_type"]),
            None,
        )
    else:
        # validate the specified stream (convert to int idx if str label given)
        st_ = primary_output
        if isinstance(st_, str):
            try:
                st = next(
                    i
                    for i, info in enumerate(output_info)
                    if "buffer" in info["dst_type"] and info["user_map"] == st_
                )
            except StopIteration as e:
                raise ValueError(
                    f'Primary media output stream "{st_}" is not found.'
                ) from e
        else:
            st = st_

            # if invalid output stream index, return None
            try:
                assert "media_type" not in output_info[st]
            except AssertionError as e:
                raise ValueError(
                    f"Primary media output stream {st} is not found."
                ) from e

    return st
