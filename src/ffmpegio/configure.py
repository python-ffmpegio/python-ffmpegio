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

These functions call ffprobe to get raw media information best it could.

The above functions do not initialize the pipes and IO threads.

- `assign_input_pipes()`
- `assign_output_pipes()`
- `init_named_pipes()`

"""

from __future__ import annotations

import logging
import re
import subprocess as fp
from collections import Counter
from collections.abc import Sequence
from contextlib import ExitStack
from functools import cache
from itertools import count

from namedpipe import NPopen

from . import filtergraph as fgb
from . import plugins, utils
from ._typing import (
    Any,
    Buffer,
    Callable,
    CountDataCallable,
    DTypeString,
    EncodedInputInfoDict,
    EncodedOutputInfoDict,
    FFmpegOptionDict,
    FFmpegUrlType,
    FilterGraphInfoDict,
    FromBytesCallable,
    InputInfoDict,
    InputPipeInfoDict,
    IsEmptyCallable,
    Literal,
    MediaType,
    NotRequired,
    OutputInfoDict,
    OutputPipeInfoDict,
    RawDataBlob,
    RawInputInfoDict,
    RawOutputInfoDict,
    RawStreamInfoTuple,
    ShapeTuple,
    ToBytesCallable,
    TypedDict,
    cast,
)
from .errors import (
    FFmpegError,
    FFmpegioError,
    FFmpegioInsufficientInputData,
    FFmpegioNoPipeAllowed,
)
from .filtergraph.abc import FilterGraphObject
from .stream_spec import parse_map_option, stream_type_to_media_type
from .threading import CopyFileObjThread, ReaderThread, WriterThread
from .utils import (
    FFmpegInputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegOutputUrlComposite,
    FFmpegOutputUrlNoPipe,
)
from .utils.concat import FFConcat  # for typing

logger = logging.getLogger("ffmpegio")

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
    input_urls: Sequence[
        FFmpegInputUrlComposite
        | tuple[FFmpegInputUrlComposite, FFmpegOptionDict | None]
    ]
    output_streams: Sequence[FFmpegOptionDict] | dict[str, FFmpegOptionDict] | None
    options: FFmpegOptionDict
    squeeze: bool
    extra_outputs: Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None


class MediaWriteKwsDict(TypedDict):
    output_urls: Sequence[FFmpegOutputOptionTuple]
    input_options: Sequence[FFmpegOptionDict]
    options: FFmpegOptionDict
    extra_inputs: NotRequired[
        Sequence[FFmpegInputUrlComposite | FFmpegInputOptionTuple] | None
    ]
    input_data: NotRequired[Sequence[RawDataBlob | None] | None]
    input_dtypes: NotRequired[Sequence[DTypeString | None] | None]
    input_shapes: NotRequired[Sequence[ShapeTuple | None] | None]


class MediaFilterKwsDict(TypedDict):
    input_options: Sequence[Literal["a", "v"]]
    output_streams: Sequence[FFmpegOptionDict] | dict[str, FFmpegOptionDict] | None
    options: FFmpegOptionDict
    extra_inputs: NotRequired[
        Sequence[FFmpegInputUrlComposite | FFmpegInputOptionTuple] | None
    ]
    extra_outputs: NotRequired[
        Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
    ]
    input_data: NotRequired[
        Sequence[tuple[RawDataBlob | None, FFmpegOptionDict]] | None
    ]
    input_dtypes: NotRequired[Sequence[DTypeString] | None]
    input_shapes: NotRequired[Sequence[ShapeTuple] | None]
    squeeze: bool


class MediaTranscoderKwsDict(TypedDict):
    input_urls: Sequence[
        FFmpegInputUrlComposite
        | tuple[FFmpegInputUrlComposite, FFmpegOptionDict | None]
    ]
    output_urls: list[FFmpegOutputOptionTuple]
    options: FFmpegOptionDict


FFmpegMediaKwsDict = (
    MediaReadKwsDict | MediaWriteKwsDict | MediaFilterKwsDict | MediaTranscoderKwsDict
)

####################R###
### I/O initializers ###
########################


def init_media_read(
    input_urls: FFmpegInputUrlComposite
    | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    | Sequence[
        FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    ],
    output_streams: str | FFmpegOptionDict | Sequence[str | FFmpegOptionDict] | None,
    options: FFmpegOptionDict | None,
    extra_outputs: (
        Sequence[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ),
    squeeze: bool,
) -> tuple[FFmpegArgs, list[EncodedInputInfoDict], list[RawOutputInfoDict]]:
    """Initialize FFmpeg arguments for media read

    :param urls: URLs of the media files to read.
    :param output_streams: output stream mappings and optional per-stream options:

        - ``None`` to map all filtergraph outputs
        - (str) output map option string
        - (dict) output ffmpeg options with the required ``'map'`` option
        - (Sequence) a sequence of output map option string or ffmpeg option
          dict with a ``'map'`` key.

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

    options = {} if options is None else {**options}

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
    output_urls: FFmpegOutputUrlComposite
    | FFmpegOutputOptionTuple
    | list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple],
    input_options: Sequence[FFmpegOptionDict],
    extra_inputs: (
        Sequence[
            FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
        ]
        | None
    ),
    options: FFmpegOptionDict | None,
    input_data: Sequence[RawDataBlob | None] | None = None,
    input_dtypes: list[DTypeString | None] | None = None,
    input_shapes: list[ShapeTuple | None] | None = None,
) -> tuple[
    FFmpegArgs,
    list[RawInputInfoDict | EncodedInputInfoDict],
    list[EncodedOutputInfoDict],
]:
    """write multiple streams to a url/file

    :param output_url: output url
    :param input_options: list of input option dicts. Each must include either
                          ``'ar'`` (audio) or ``'r'`` (video) to specify the
                          media type and rate.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                      will be applied to all input streams unless the option has been already defined in `stream_data`
    :param input_data: list of input data to be written in a batch-mode (or ``None``
                       if streaming), defaults to no data.
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

    options = {} if options is None else {**options}

    # separate the options
    inopts_default = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = empty(utils.pop_global_options(options))

    # analyze and assign inputs
    input_info = process_raw_inputs(
        args, input_options, inopts_default, input_data, input_dtypes, input_shapes
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
    input_options: Sequence[FFmpegOptionDict],
    extra_inputs: Sequence[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple] | None,
    output_streams: str | FFmpegOptionDict | Sequence[str | FFmpegOptionDict] | None,
    extra_outputs: (
        Sequence[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple] | None
    ),
    options: FFmpegOptionDict | None,
    squeeze: bool,
    input_data: list[RawDataBlob | None] | None = None,
    input_dtypes: list[DTypeString | None] | None = None,
    input_shapes: list[ShapeTuple | None] | None = None,
) -> tuple[FFmpegArgs, list[RawInputInfoDict], list[RawOutputInfoDict]]:
    """Prepare FFmpeg arguments for media read

    :param input_options: list of input option dicts. Each must include either
                          ``'ar'`` (audio) or ``'r'`` (video) to specify the
                          media type and rate.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param output_streams: output stream mappings and optional per-stream options:

        - ``None`` to map all filtergraph outputs
        - (str) output map option string
        - (dict) output ffmpeg options with the required ``'map'`` option
        - (Sequence) a sequence of output map option string or ffmpeg option
          dict with a ``'map'`` key.

    :param extra_outputs: list of additional output destinations, defaults to None.
                          Each source may be url string or a pair of a url string
                          and an option dict.
    :param options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                    will be applied to all input streams unless the option has been already defined in `stream_data`
    :param squeeze: True to squeeze output data blob shape
    :param input_data: list of input data to be written in a batch-mode (or ``None``
                       if streaming), defaults to no data.
    :param input_dtypes: list of numpy-style data type strings of input samples or frames
                         of input media streams, use `None` to auto-detect.
    :param input_shapes: list of shapes of input samples or frames of input media streams,
                         use `None` to auto-detect.
    :return ffmpeg_args: FFmpeg argument dict (partial)
    :return input_info: input stream information
    :return output_info: output stream information, None if outputs not initialized

    """

    options = {} if options is None else {**options}

    if "n" in options:
        raise ValueError("Cannot have an `n` option set to output to named pipes.")

    # separate the options
    inopts_default = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = empty(utils.pop_global_options(options))
    gopts = args["global_options"]  # global options dict
    gopts["y"] = None

    # analyze and assign inputs
    input_info = process_raw_inputs(
        args, input_options, inopts_default, input_data, input_dtypes, input_shapes
    )

    if extra_inputs is not None:
        try:
            input_info.extend(process_url_inputs(args, extra_inputs, {}, no_pipe=True))
        except FFmpegioNoPipeAllowed:
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
    input_urls: FFmpegInputUrlComposite
    | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    | Sequence[
        FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    ],
    output_urls: FFmpegOutputUrlComposite
    | FFmpegOutputOptionTuple
    | list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple],
    options: FFmpegOptionDict | None,
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

    options = {} if options is None else {**options}

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


def empty(global_options: FFmpegOptionDict | None = None) -> FFmpegArgs:
    """create empty ffmpeg arg dict

    :param global_options: global options, defaults to None
    :return: ffmpeg arg dict with empty 'inputs','outputs',and 'global_options' entries.
    """
    return {"inputs": [], "outputs": [], "global_options": global_options or {}}


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
        if pix_fmt is None:
            # use the analyzed value, falling back to 'rgb24'
            if pix_fmt_in == "unknown":
                raise FFmpegioError(
                    "input pixel format unknown. Please specify output pix_fmt"
                )

            # deduce output pixel format from the input pixel format
            pix_fmt, ncomp, dtype, _ = utils.get_pixel_config(pix_fmt_in)
            outopts["pix_fmt"] = pix_fmt

        elif pix_fmt_in is None:
            # make sure assigned pix_fmt is valid (shouldn't get here)
            try:
                dtype, ncomp = utils.get_pixel_format(pix_fmt)
            except Exception as e:
                raise FFmpegioError(
                    "could not resolve output pixel format. Please specify output `'pix_fmt'` option"
                ) from e

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
                "filtergraph input expresion cannot take ordered options."
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


class RawInputCallablesDict(TypedDict):
    data2bytes: ToBytesCallable
    data_count: CountDataCallable
    data_is_empty: IsEmptyCallable


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
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
) -> tuple[list[FFmpegOptionDict], list[dict]]:
    """resolve the raw output streams from given sequence of map options

    :param stream_opts: output raw stream options
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
                    "user_map": spec[1:-1],
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
                        "user_map": spec,
                        "media_type": stream_type_to_media_type(
                            stream_spec["stream_type"]
                        ),
                        "input_file_id": file_index,
                        "input_stream_id": -1,  # unknown and don't care
                    }
                )
            else:
                # case 3: generic stream spec, possibly resultsing in multiple output streams
                url, opts = inputs[file_index]
                for stream_index, stream_spec in utils.input_file_stream_specs(
                    url, stream_spec, opts or {}, input_info[file_index]
                ).items():
                    # append all streams
                    spec = f"{file_index}:{stream_index}"
                    output_opts.append({**opts, "map": spec})
                    output_info.append(
                        {
                            "user_map": spec,
                            "media_type": "audio" if stream_spec[0] == "a" else "video",
                            "input_file_id": file_index,
                            "input_stream_id": stream_index,
                        },
                    )

    # resolve duplicate user_map values
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


def auto_map(
    args: FFmpegArgs,
    options: FFmpegOptionDict,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
    fg_info: dict[str, FilterGraphInfoDict] | None,
) -> tuple[list[FFmpegOptionDict], list[dict[str, Any]]]:
    """list all available streams from all FFmpeg input sources

    This function complements `resolve_raw_output_streams()`

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
        # if no filtergraph, get all video & audio streams from all the input urls
        for i, ((url, opts), info) in enumerate(zip(args["inputs"], input_info)):
            for j, st_spec in utils.input_file_stream_specs(
                url, None, opts or {}, info
            ).items():
                spec = f"{i}:{st_spec}"
                stream_opts.append({**options, "map": spec})
                stream_info.append(
                    {
                        "user_map": spec,
                        "media_type": "audio" if st_spec[0] == "a" else "video",
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
    urls: FFmpegInputUrlComposite
    | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    | Sequence[
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
    :param urls: input urls/data or a pair of input url and its options or a list thereof
    :param inopts_default: default input options
    :param no_pipe: True to raise exception if an input is piped without data buffer, defaults to False
    :return: list of input information
    """

    urls = [urls] if utils.is_valid_input_url(urls) or isinstance(urls, tuple) else urls

    if len(urls) == 0:
        raise FFmpegioError("At least one URL must be given.")

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
    streams: str | FFmpegOptionDict | Sequence[str | FFmpegOptionDict] | None,
    options: FFmpegOptionDict,
    squeeze: bool,
) -> list[OutputInfoDict]:
    """analyze and process piped raw outputs

    :param args: FFmpeg argument dict, A new item in`args['outputs']` is
                 appended for each piped output. Output URLs are left `None`.
    :param input_info: list of input information (same length as `args['inputs'])
    :param streams: output stream mappings:

          - `None` to include all input streams OR all filtergraph outputs
          - a sequence of either a map option or an output ffmpeg option
            dict with `'map'` item

    :param options: default output options
    :param squeeze: True to remove shape dimensions with length 1
    :return output_info: list of output information

    """

    if isinstance(streams, (str, dict)):
        streams = [streams]

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
        if streams is None:
            stream_opts = [options]
        else:
            stream_opts = [
                {**options, **({"map": v} if isinstance(v, str) else v)}
                for v in streams
            ]

        # expand all streams (targetting )
        stream_opts, stream_info = resolve_raw_output_streams(
            stream_opts, args, input_info
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
    stream_options: Sequence[FFmpegOptionDict],
    default_options: FFmpegOptionDict,
    data: Sequence[RawDataBlob | None] | None = None,
    dtypes: list[DTypeString | None] | None = None,
    shapes: list[ShapeTuple | None] | None = None,
) -> list[RawInputInfoDict]:
    """configure input raw media streams

    :param args: FFmpeg argument dict (to be modified)
    :param stream_options: per-stream dict of FFmpeg input options
    :param default_options: dict of FFmpeg input options applied to all streams
    :param data: per-stream data blob to be written when ffmpeg starts, defaults
                 to data
    :param dtypes: per-stream data types (numpy dtype string), defaults to
                   auto-detect
    :param shapes: per-stream data shapes, defaults to auto-detect
    :return: a list of dict containing the provided info
    """

    @cache
    def get_callables(media_type: MediaType) -> RawInputCallablesDict:
        hook = plugins.pm.hook
        return (
            {
                "data2bytes": cast(ToBytesCallable, hook.audio_bytes),
                "data_is_empty": cast(IsEmptyCallable, hook.is_empty),
                "data_count": cast(CountDataCallable, hook.audio_samples),
            }
            if media_type == "audio"
            else {
                "data2bytes": cast(ToBytesCallable, hook.video_bytes),
                "data_is_empty": cast(IsEmptyCallable, hook.is_empty),
                "data_count": cast(CountDataCallable, hook.video_frames),
            }
        )

    nstreams = len(stream_options)
    none_list = [None] * nstreams
    input_info: list[RawInputInfoDict] = []

    for opts, blob, dtype, shape in zip(
        stream_options,
        none_list if data is None else data,
        none_list if dtypes is None else dtypes,
        none_list if shapes is None else shapes,
    ):
        # combine the default & per-stream options
        opts = {**default_options, **opts}
        mtype = "v" if "r" in opts else "a"
        more_opts = None
        shape_dtype = None
        if mtype == "a":  # audio
            if "r" in opts or "ar" not in opts:
                raise ValueError(
                    "audio stream option dict must contain 'ar' option and must not contain 'r' option."
                )
            media_type = "audio"
            opts["ar"] = rate = round(opts["ar"])  # force int sampling rate
            if blob is not None:
                more_opts, shape_dtype = utils.array_to_audio_options(blob)

            elif dtypes and shapes and shape is not None and dtype is not None:
                shape_dtype = (shape, dtype)
                sample_fmt, ac = utils.guess_audio_format(shape, dtype)
                acodec, f = utils.get_audio_codec(sample_fmt)
                more_opts = {"sample_fmt": sample_fmt, "ac": ac, "c:a": acodec, "f": f}

        else:  # video
            if "ar" in opts:
                raise ValueError(
                    "video stream option dict must not contain 'ar' option."
                )
            media_type = "video"
            rate = opts["r"]
            if blob is not None:
                more_opts, shape_dtype = utils.array_to_video_options(blob)
            elif dtype and shape:
                shape_dtype = (shape, dtype)
                pix_fmt, s = utils.guess_video_format(*raw_info)
                more_opts = {
                    "f": "rawvideo",
                    "c:v": "rawvideo",
                    "pix_fmt": pix_fmt,
                    "s": s,
                }

        if shape_dtype is None:
            raise FFmpegioInsufficientInputData(
                "Both input_dtypes and input_shapes must be defined for all raw input streams."
            )

        raw_info = (*shape_dtype, rate)

        if more_opts is not None:
            opts.update(more_opts)

        info = {
            "src_type": "buffer",
            "media_type": media_type,
            "raw_info": (*raw_info, rate),
            "item_size": utils.get_samplesize(*raw_info[:-1]),
            **get_callables(media_type),
        }

        if data is not None:
            info["buffer"] = info["data2bytes"](obj=blob)

        add_url(args, "input", None, opts)
        input_info.append(info)

    return input_info


def process_url_outputs(
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
    urls: FFmpegOutputUrlComposite
    | FFmpegOutputOptionTuple
    | list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple],
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

    urls = (
        [urls] if utils.is_valid_output_url(urls) or isinstance(urls, tuple) else urls
    )

    if len(urls) == 0:
        raise FFmpegioError("At least one URL must be given.")

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

    pipe_info: dict[int, OutputPipeInfoDict] = {}
    sp_kwargs = {}

    if output_info is None:
        return sp_kwargs, sp_kwargs

    # configure output pipes
    use_stdout = False
    has_pipeout = False

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
    ref_stream: int | None = None,
    ref_blocksize: int | None = None,
    enc_blocksize: int | None = None,
    queue_size: int | None = None,
    timeout: float | None = None,
    stack: ExitStack | None = None,
) -> ExitStack:
    """initialize named pipes for read & write operations with FFmpeg

    :param args: FFmpeg option arguments (modified)
    :param input_info: FFmpeg input information, its length matches that of `args['inputs']`
    :param output_info: FFmpeg output information, its length matches that of `args['outputs']` (modified)
    :param ref_stream: index of reference raw media output stream, defaults to 0
                       if raw media stream is present or -1 if only encoded
    :param ref_blocksize: block size of the reference stream, defaults to 1 if video
                          and 1024 for audio
    :param encoded_blocksize: encoded data output block size in bytes, defaults to None (2**20 bytes)
    :param queuesize: the depth of named pipe queues, defaults to 16. For
                      unlimited queue size, specify zero (0).
    :param timeout: Default queue read timeout in seconds, defaults to `None` to
                    wait indefinitely. Note this timeout does not apply to
                    stdout pipe operation.
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

    wr_kws = {"queuesize": queue_size, "timeout": timeout}

    # configure output pipes
    if ref_stream is None and len(output_info):
        ref_stream = 0 if "raw_info" in output_info[0] else -1

    ref_rate = 1
    if ref_stream is not None and ref_stream >= 0:
        ref_rate = output_info[ref_stream]["raw_info"][-1]

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
                kws["itemsize"] = info["item_size"]
                if ref_rate is None:
                    ref_stream = i
                    ref_rate = info["raw_info"][-1]
                    kws["nmin"] = ref_blocksize
                elif i == ref_stream:
                    kws["nmin"] = ref_blocksize
                else:
                    rate = info["raw_info"][-1]
                    kws["nmin"] = round(rate / ref_rate) or 1
                    kws["queuesize"] = 0
                    # secondary stream queue size implicitly controlled by ref_stream
            else:
                # encoded output in bytes
                kws["itemsize"] = 1
                kws["nmin"] = enc_blocksize or 2**16
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
            self.join()
        else:
            self._proc.stdin.write(data)

    def join(self):
        # no thread, just close the stdin
        self._proc.stdin.flush()
        self._proc.stdin.close()

    def closed(self) -> bool:
        return self._proc.stdin.closed


class StdReader:
    def __init__(self, proc: fp.Popen, itemsize: int) -> None:
        self._proc = proc
        self._itemsize = itemsize

    def read(self, n: int = -1) -> bytes:
        return self._proc.stdout.read(n if n <= 0 else n * self._itemsize)

    def cool_down(self):
        pass

    def join(self):
        pass


def init_std_pipes(
    input_pipes: dict[int, InputPipeInfoDict],
    output_pipes: dict[int, OutputPipeInfoDict],
    output_info: list[OutputInfoDict],
    proc: fp.Popen,
):
    """initialize std pipe reader or writer

    :param input_pipes: _description_
    :param output_pipes: _description_
    :param output_info: FFmpeg output information, its length matches that of `args['outputs']`
    :param proc: _description_
    """
    stdin = next((st for st, p in input_pipes.items() if p["pipe"] == "stdin"), None)
    if stdin is not None:
        input_pipes[stdin]["writer"] = StdWriter(proc)

    stdout = next((st for st, p in output_pipes.items() if p["pipe"] == "stdout"), None)
    if stdout is not None:
        output_pipes[stdout]["reader"] = StdReader(
            proc, output_info[stdout]["item_size"]
        )
