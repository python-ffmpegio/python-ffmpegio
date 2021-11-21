import re
from collections.abc import Sequence
import numpy as np
from . import probe, utils, filter_utils, ffmpeg

_video_opts = (
    "pix_fmt",
    "frame_rate",
    "fill_color",
    "size",
    "scale",
    "crop",
    "flip",
    "transpose",
    "rotate",
    "deinterlace",
)

_audio_opts = ("sample_fmt", "channels", "sample_rate")


def empty():
    """create empty ffmpeg arg dict

    :return: empty ffmpeg arg dict with 'inputs','outputs',and 'global_options' entries.
    :rtype: dict
    """
    return dict(inputs=[], outputs=[], global_options=None)


def check_url(url, nodata=True):
    """Analyze url argument for non-url input

    :param url: url argument string or data or file
    :type url: str, bytes-like object, numpy.ndarray, or file-like object
    :param nodata: True to raise exception if url is a bytes-like object, default to True
    :type nodata: bool, optional
    :return: url string, file object, and data object
    :rtype: tuple<str, file-like object or None, bytes-like object or None>
    """

    def hasmethod(o, name):
        return hasattr(o, name) and callable(getattr(o, name))

    fileobj = None
    data = None

    if not isinstance(url, str):
        if isinstance(url, (bytes, bytearray, np.ndarray)) or hasmethod(
            url, "__bytes__"
        ):
            data = url
            url = "-"
        elif hasmethod(url, "fileno"):
            fileobj = url
            url = "-"

    if nodata and data is not None:
        raise ValueError("Bytes-like object cannot be specified as url.")

    return url, fileobj, data


def add_url(args, type, url, opts=None):
    """add new or modify existing url to input or output list

    :param args: ffmpeg arg dict (modified in place)
    :type args: dict
    :param type: input or output
    :type type: 'input' or 'output'
    :param url: url of the new entry
    :type url: str
    :param opts: FFmpeg options associated with the url, defaults to None
    :type opts: dict, optional
    :return: file index and its entry
    :rtype: tuple(int, tuple(str, dict or None))
    """

    # instead of url, input tuple (url, opts) is given
    if not isinstance(url, str):
        opts = url[1] if opts is None else {**url[1], **opts}
        url = url[0]

    type = f"{type}s"
    filelist = args.get(type, None)
    if filelist is None:
        filelist = args[type] = []
    n = len(filelist)
    id = next((i for i in range(n) if filelist[i][0] == url), None)
    if id is None:
        id = n
        filelist.append((url, opts and {**opts}))
    elif opts is not None:
        filelist[id] = (
            url,
            opts and {**opts}
            if filelist[id][1] is None
            else {**filelist[id][1], **opts},
        )
    return id, filelist[id]


def finalize_opts(
    input, opt_names, default=None, prefix="", aliases=None, excludes=None
):
    """extract relevant option keyword inputs

    :param input: raw input options
    :type input: dict
    :param opt_names: list of acceptable option keywords
    :type opt_names: seq of str
    :param default: default option values, defaults to None
    :type default: dict, optional
    :param prefix: specify if input keywords are prefixed version of the expected, defaults to ""
    :type prefix: str, optional
    :param aliases: keyword aliases, defaults to None
    :type aliases: dict, optional
    :param excludes: list of valid keywords to be excluded, defaults to None
    :type excludes: seq of str, optional
    :return: curated list of options
    :rtype: dict
    """
    opts = {} if default is None else dict(**default)
    for k, v in input.items():
        if excludes and k in excludes:
            pass
        else:
            found = False
            if aliases:
                name = aliases.get(k, None)
                found = name is not None
                if found:
                    opts[name] = v
            if not found and (not prefix or k.startswith(prefix)):
                name = k[len(prefix) :]
                if name in opt_names:
                    opts[name] = v
    return opts


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


###########################################################################


def input_timing(
    ffmpeg_args,
    url,
    vstream_id=None,
    astream_id=None,
    prefix="",
    aliases={},
    excludes=None,
    **options,
):
    """set input decoding timing

    :param ffmpeg_args: ffmpeg argument dict
    :type ffmpeg_args: dict
    :param url: input url
    :type url: str
    :param vstream_id: refernce video stream id ('v:#'), defaults to None
    :type vstream_id: int, optional
    :param astream_id: reference audio stream id ('a:#'), defaults to None
    :type astream_id: int, optional
    :param prefix: option name prefix, defaults to ""
    :type prefix: str, optional
    :param aliases: option name aliases, defaults to {}
    :type aliases: dict, optional
    :param excludes: list of excluded options, defaults to None
    :type excludes: seq of str, optional
    :param \\**options: user options
    :type \\**options: dict
    :return: ffmpeg_args
    :rtype: dict

    ===================  ================================================
    option name          description
    ===================  ================================================
    "start"              start time (-ss)
    "end"                end time (-to)
    "duration"           duration (-t)
    "input_frame_rate"   frame rate of reference video stream (-ar:a)
    "input_sample_rate"  sampling rate of reference audio stream (-r:v)
    "units"              time units for `start`, `end`, and `duration`:
                           "seconds" (Default), "frames", or "samples"
    ===================  ================================================

    """

    opts = finalize_opts(
        options,
        ("start", "end", "duration", "input_frame_rate", "input_sample_rate", "units"),
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    inopts = {}
    input_frame_rate = opts.get("input_frame_rate", None)
    input_sample_rate = opts.get("input_sample_rate", None)
    if input_frame_rate is not None:
        inopts[
            "r:v" if vstream_id is None else f"r:{utils.spec_stream(vstream_id,'v')}"
        ] = input_frame_rate
    if input_sample_rate is not None:
        inopts[
            "ar:a" if astream_id is None else f"ar:{utils.spec_stream(astream_id,'a')}"
        ] = input_sample_rate

    file_id, file_entry = add_url(ffmpeg_args, "input", url, inopts)

    # if start/end/duration are specified
    start = opts.get("start", None)
    end = opts.get("end", None)
    duration = opts.get("duration", None)
    input_sample_rate = opts.get("input_sample_rate", None)
    need_units = start is not None or end is not None or duration is not None
    if need_units:
        units = opts.get("units", "seconds")
        fs = (
            1.0
            if units == "seconds"
            else get_option(
                ffmpeg_args,
                "input",
                "r",
                file_id=file_id,
                stream_type="v",
                stream_id=vstream_id,
            )
            or probe.video_streams_basic(url, vstream_id)[0]["frame_rate"]
            if units == "frames"
            else get_option(
                ffmpeg_args,
                "input",
                "ar",
                file_id=file_id,
                stream_type="a",
                stream_id=astream_id,
            )
            or probe.audio_streams_basic(url, astream_id)[0]["sample_rate"]
            if units == "samples"
            else None
        )
        if fs is None:
            raise Exception("invalid `units` specified")

        inopts = file_entry[1]
        if start:
            inopts["ss"] = start if isinstance(start, str) else float(start / fs)
        elif end and duration:
            if isinstance(end, str) or isinstance(duration, str):
                raise Exception(
                    "when specifying end and duration, they both must be numeric"
                )
            inopts["ss"] = float((end - duration) / fs)
        if end:
            inopts["to"] = end if isinstance(start, str) else float(end / fs)
        if duration:
            inopts["t"] = duration if isinstance(start, str) else float(duration / fs)

    return ffmpeg_args


def codec(
    ffmpeg_args,
    url,
    stream_type,
    stream_id=None,
    prefix="",
    aliases={},
    excludes=None,
    **options,
):
    """configure output codec configuration

    :param ffmpeg_args: ffmpeg args dict
    :type ffmpeg_args: dict
    :param url: output url
    :type url: str
    :param stream_type: stream type: 'v' or 'a'
    :type stream_type: str
    :param stream_id: stream index, defaults to None to be applicable to all streams
    :type stream_id: int or None, optional
    :param prefix: option name prefix, defaults to ""
    :type prefix: str, optional
    :param aliases: option name aliases, defaults to {}
    :type aliases: dict, optional
    :param excludes: list of excluded options, defaults to None
    :type excludes: seq of str, optional
    :param \\**options: user options
    :type \\**options: dict
    :return: ffmpeg_args
    :rtype: dict


    ===========  ========================
    option name          description
    ===========  ========================
    "codec"      codec name (-c)
    "q"          fixed quality scale (-q)
    ===========  ========================

    """

    outopts = add_url(ffmpeg_args, "output", url, {})[1][1]

    # TODO get encoder options from caps

    opts = finalize_opts(
        options,
        ("codec", "q"),
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    spec = utils.spec_stream(type=stream_type, index=stream_id)

    if "codec" in opts:
        val = opts["codec"]
        if val == "none" or val is None:
            outopts[f"{stream_type}n"] = None
        else:
            outopts[f"c:{spec}"] = val
    elif "q" in opts:
        outopts[f"q:{spec}"] = opts["q"]

    return ffmpeg_args


def audio_io(
    ffmpeg_args,
    input,
    *stream_ids,
    file_index=None,
    prefix="",
    format=None,
    output_url=None,
    aliases={},
    excludes=None,
    **kwargs,
):
    if isinstance(input, str):
        input = (input, None)
    input = add_url(ffmpeg_args, "input", *input)[1]
    out_cfg = add_url(ffmpeg_args, "output", output_url, {})[1][1]

    cfgs, reader_config = audio_file(
        input,
        *stream_ids,
        file_opts=kwargs,
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
        for_reader=output_url == "-",
    )

    if cfgs is None:
        return ffmpeg_args, reader_config

    nstreams = len(cfgs)
    if not len(stream_ids):
        stream_ids = range(nstreams)

    if "format" not in out_cfg and format:
        out_cfg["f"] = format

    out_map = out_cfg.pop("map", [])
    out_map = [out_map] if isinstance(out_map, str) else out_map

    for i in range(nstreams):
        spec = utils.spec_stream(stream_ids[i], "a", file_index=file_index)
        if spec in out_map:
            id = out_map.index(spec)
        else:
            id = len(out_map)
            out_map.append(spec)

        for k, v in cfgs[i].items():
            out_cfg[f"{k}:{spec}"] = v

    out_cfg["map"] = out_map
    return ffmpeg_args, reader_config


def audio_file(
    input,
    *streams,
    file_opts=None,
    for_reader=False,
    default_opts={},
    prefix="",
    aliases={},
    excludes=None,
):
    """generate options and optionally reader data for output audio streams

    :param input: stream source, url and ffmpeg options
    :type input: tuple(str, dict or None)
    :param \\*streams: input stream indices ('a:#') and optionally custom options
    :type \\*streams: tuple(int or tuple(int, dict))
    :param file_opts: common options for all streams, defaults to None
    :type file_opts: dict, optional
    :param for_reader: True to return reader config, defaults to False
    :type for_reader: bool, optional
    :param default_opts: default options, defaults to {}
    :type default_opts: dict, optional
    :param prefix: option name prefix, defaults to ""
    :type prefix: str, optional
    :param aliases: option name aliases, defaults to {}
    :type aliases: dict, optional
    :param excludes: list of excluded options, defaults to None
    :type excludes: seq of str, optional
    :return: ffmpeg options and reader configs, each per stream
    :rtype: tuple(seq(dict), seq(seq))

    ===========  ==========
    sample_rate  ar
    sample_fmt   sample_fmt
    channels     ac
    ===========  ==========

    """

    all_info, always_copy = utils.analyze_audio_input(
        input, entries=("sample_rate", "sample_fmt", "channels")
    )

    if not (len(all_info) and len(streams)):
        return None, None

    # make streams list elements to be all (int, dict)
    nstreams = len(streams)
    streams = (
        [(s, {}) if isinstance(s, int) else s for s in streams]
        if nstreams
        else [(s, {}) for s in range(len(all_info))]
    )

    # finalize file-specific option if given
    file_opts = (
        finalize_opts(
            file_opts,
            _audio_opts,
            default_opts,
            prefix,
            aliases=aliases,
            excludes=excludes,
        )
        if file_opts
        else default_opts
    )

    ffmpeg_config, reader_config = zip(
        *[
            audio_stream(
                all_info[st[0]],
                *st[1:],
                for_reader=for_reader,
                always_copy=always_copy,
                default_opts=file_opts,
            )
            for st in streams
        ]
    )

    return ffmpeg_config, reader_config if for_reader else None


def audio_stream(
    info,
    stream_opts=None,
    *,
    for_reader=False,
    always_copy=False,
    default_opts={},
):
    """generate output audio stream options and optionally reader data

    :param info: input stream info
    :type info: dict
    :param stream_opts: output stream options, defaults to None
    :type stream_opts: dict, optional
    :param for_reader: True to return reader config, defaults to False
    :type for_reader: bool, optional
    :param always_copy: True to copy options even if unchanged
    :tyoe always_copy: bool
    :param default_opts: default options, defaults to {}
    :type default_opts: dict, optional
    :return: FFmpeg options and if requested reader config
    :rtype: tuple(dict, tuple(numpy.dtype, int, int))

    ===========  ==========
    sample_rate  ar
    sample_fmt   sample_fmt
    channels     ac
    ===========  ==========

    """
    opts = (
        finalize_opts(stream_opts, _audio_opts, default_opts)
        if stream_opts
        else default_opts
    )

    rate = opts.get("sample_rate", None)
    fmt = opts.get("sample_fmt", None)
    nch = opts.get("channels", None)

    ffmpeg_config = {}
    if rate is not None and (always_copy or rate != info["sample_rate"]):
        ffmpeg_config["ar"] = rate
    if fmt is not None and (always_copy or fmt != info["sample_fmt"]):
        ffmpeg_config["sample_fmt"] = fmt
    if nch is not None and (always_copy or nch != info["channels"]):
        ffmpeg_config["ac"] = nch

    reader_config = None
    if for_reader:
        codec, dtype = utils.get_audio_format(fmt or info["sample_fmt"])
        ffmpeg_config["codec"] = codec
        reader_config = (dtype, nch or info["channels"], rate or info["sample_rate"])

    return ffmpeg_config, reader_config


def video_io(
    ffmpeg_args,
    input,
    *stream_ids,
    prefix="",
    format=None,
    output_url=None,
    aliases={},
    excludes=None,
    **kwargs,
):
    """Create ffmpeg.run() ready arg dict and expected numpy array stream outputs
    :param ffmpeg_args: ffmpeg run arguments to add
    :type ffmpeg_args: dict
    :param *input_defs: list of input urls and optional selection of streams
    :type input_defs[]: str or tuple(str, <int|seq>, <dict>)
    :return: [description]
    :rtype: tuple(dict,list of tuples)

    Supported kwargs (w/out `prefix`)
    ---------------------------------
    :param pix_fmt: pixel format
    :type pix_fmt: str
    :param fill_color: background color, defaults to "white"
    :type fill_color: str
    :param size: output video frame size (width,height). if one is <=0 scales proportionally to
    :type size: tuple(int,int)
    :param scale: output video frame scaling factor, if `size` is not defined
    :type scale: float or tuple(float,float)
    :param crop: video frame cropping/padding. If positive, the video frame is cropped from the respective edge. If negative, the video frame is padded on the respective edge.
    :type crop: tuple(int,int,int,int) 4-element integer vector [left top right bottom], if right or bottom is missing, uses the same value as left or top, respectively
    :param flip: flip the video frames horizontally, vertically, or both.
    :type flip: {'horizontal','vertical','both'}
    :param transpose: tarnspose the video frames
    :type transpose: int
    :param rotate: degrees to rotate video frame clockwise
    :type rotate: float

    Filter Order: crop=>flip=>transpose=>rotate=>scale


    """

    if not len(stream_ids):
        stream_ids = [0]

    if isinstance(input, str):
        input = (input, None)
    in_file_id, input = add_url(ffmpeg_args, "input", *input)
    out_cfg = add_url(ffmpeg_args, "output", output_url, {})[1][1]

    ffmpeg_opts, ffmpeg_srcs, reader_cfgs = video_file(
        input,
        *stream_ids,
        file_opts=kwargs,
        for_reader=output_url == "-",
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    if ffmpeg_opts == None:
        return ffmpeg_args, reader_cfgs

    nstreams = len(ffmpeg_opts)
    if nstreams < 1:
        return ffmpeg_args, reader_cfgs

    if not len(stream_ids):
        stream_ids = range(nstreams)

    out_map = out_cfg.pop("map", [])
    out_map = [out_map] if isinstance(out_map, str) else out_map
    fg = get_option(ffmpeg_args, "global", "filter_complex")

    if fg is None:
        fg = []
        fg_labels = None
    elif isinstance(fg, str):
        fg, fg_labels = filter_utils.parse_graph(fg)
    elif isinstance(fg[-1], dict):
        fg_labels = fg[-1]
        fg = fg[:-1]

    if fg_labels is None:
        fg_labels = {"input_labels": None, "output_labels": None}
    fg_inputs = fg_labels.get("input_labels", None)
    if fg_inputs is None:
        fg_inputs = fg_labels["input_labels"] = {}
    fg_outputs = fg_labels.get("output_labels", None)
    if fg_outputs is None:
        fg_outputs = fg_labels["output_labels"] = {}

    for i, opts in enumerate(ffmpeg_opts):

        st_id = stream_ids[i]
        filt_def = opts.pop("vf", None)

        in_spec = out_spec = utils.spec_stream(st_id, "v", file_index=in_file_id)

        if filt_def and len(filt_def) > 0:

            chain_id = len(fg)
            bg_src = ffmpeg_srcs[i]

            # find the endpoint of current fg originating from in_spec
            # raises exception if filter graph splits
            out_spec = filter_utils.trace_graph_downstream(
                fg_labels, in_spec, allow_split=False
            )

            if out_spec != in_spec:
                filter_utils.extend_chain(fg, fg_labels, filt_def, out_spec)
            else:
                out_spec = f"vout{chain_id}"
                fg.append(filt_def)
                fg_inputs[in_spec] = (chain_id, 1) if bg_src else chain_id
                fg_outputs[out_spec] = chain_id

            if bg_src:
                id, _ = add_url(ffmpeg_args, "input", bg_src, {"f": "lavfi"})
                fg_inputs[utils.spec_stream(0, "v", file_index=id)] = (chain_id, 0)

        # adjust the stream mapping
        if out_spec != in_spec:
            out_spec = f"[{out_spec}]"
        if in_spec != out_spec and in_spec in out_map:
            # redirection
            out_id = out_map.index(in_spec)
            out_map[out_id] = out_spec
        elif out_spec in out_map:
            out_id = out_map.index(out_spec)
        else:
            out_id = len(out_map)
            out_map.append(out_spec)

        # add stream specific options
        for k, v in opts.items():
            out_cfg[f"{k}:{out_id}"] = v

    if format is not None:
        out_cfg["f"] = format

    out_cfg["map"] = out_map
    if len(fg) > 0:
        merge_user_options(ffmpeg_args, "global", {"filter_complex": (fg, fg_labels)})

    return ffmpeg_args, reader_cfgs


def video_file(
    input,
    *stream_ids,
    file_opts=None,
    for_reader=False,
    default_opts={},
    prefix="",
    aliases={},
    excludes=None,
):
    """Configure image/video streams in a media file with basic filters

    :param url: file url
    :type url: str
    :param *stream_ids: a list of streams (stream id with optional stream-specific option dicts), if none defined, returns all streams in file
    :type input: seq of int or (int, dict)
    :param file_index: file number, defaults to 0
    :type file_index: int, optional
    :param file_opts: file-specific options with relevant options possibly prefixed, defaults to {}
    :type file_opts: dict, optional
    :param default_opts: common image config options, defaults to {}
    :type default_opts: dict, optional
    :param prefix: prefix if , defaults to ""
    :type prefix: str, optional
    :return: sequence of output stream data: id, pix_fmt, filter, required aux src, shape, dtype
    :rtype: tuple(int, str, str, tuple(str, str)), tuple(int,int,int), numpy.dtype
    """

    all_info, always_copy = utils.analyze_video_input(
        input, entries=("width", "height", "pix_fmt", "frame_rate")
    )

    if not (len(all_info) and len(stream_ids)):
        return None, None, None

    # make streams list uniform
    nstreams = len(stream_ids)
    streams = (
        [(s, {}) if isinstance(s, int) else s for s in stream_ids]
        if nstreams
        else [(s, {}) for s in range(len(all_info))]
    )

    # finalize file-specific option if given
    file_opts = (
        finalize_opts(
            file_opts,
            _video_opts,
            default_opts,
            prefix,
            aliases=aliases,
            excludes=excludes,
        )
        if file_opts
        else default_opts
    )

    ffmpeg_opts, ffmpeg_srcs, reader_cfgs = zip(
        *[
            video_stream(
                all_info[st[0]],
                *st[1:],
                for_reader=for_reader,
                always_copy=always_copy,
                default_opts=file_opts,
            )
            for st in streams
        ]
    )

    return ffmpeg_opts, ffmpeg_srcs, reader_cfgs


def video_stream(
    info,
    stream_opts=None,
    *,
    always_copy=False,
    default_opts={},
    for_reader=False,
):
    """Configure image/video stream with basic filters

    :param index: video stream number
    :type index: int
    :param info: output of `video_streams_basic()` for the stream
    :type info: dict
    :param stream_opts: custom stream options
    :type stream_opts: dict, optional
    :param file_index: file index, defaults to 0
    :type file_index: int, optional
    :param for_reader: True to prepare reader_config output tuple item
    :type for_reader: bool
    :param always_copy: True to copy options even if unchanged
    :tyoe always_copy: bool
    :param default_opts: default stream options, defaults to {}
    :type default_opts: dict, optional
    :return: sequence of output stream data: pix_fmt, filter, bg_src, shape, dtype
    :rtype: tuple(str or None, list, tuple(str, str) or None), tuple(int,int,int), numpy.dtype

    :note If `bg_src` is returned, it is the required background filler source for the main
          (first) overlay input. Configure
    """

    stream_opts = (
        finalize_opts(stream_opts, _video_opts, default_opts)
        if stream_opts
        else default_opts
    )

    if for_reader or "pix_fmt" in stream_opts:
        out_pix_fmt, ncomp, dtype, remove_alpha = utils.get_pixel_config(
            info["pix_fmt"], stream_opts.get("pix_fmt", None)
        )
    else:
        out_pix_fmt, remove_alpha = None, None

    w = info["width"]
    h = info["height"]

    bg_color = stream_opts.get("fill_color", "white")

    vfilters = []

    bg_src = f"color=c={bg_color}:s={w}x{h}" if remove_alpha else None

    if remove_alpha:
        vfilters.append("overlay")

    crop = stream_opts.get("crop", None)
    if crop:
        n = len(crop)
        left = crop[0]
        top = crop[1] if n > 1 else 0
        right = crop[2] if n > 2 else left
        bottom = crop[3] if n > 3 else top
        w -= left + right
        h -= top + bottom
        if w < 0 or h < 0:
            raise Exception("invalid crop filter specified")
        vfilters.append(("crop", w, h, left, top))

    flip = stream_opts.get("flip", None)
    if flip:
        try:
            ftype = ("", "horizontal", "vertical", "both").index(flip)
        except:
            raise Exception("Invalid flip filter specified.")
        if ftype % 2:
            vfilters.append("hflip")
        if ftype >= 2:
            vfilters.append("vflip")

    transpose = stream_opts.get("transpose", None)
    if transpose is not None:
        vfilters.append(("transpose", transpose))
        if h > w or (isinstance(transpose, int) and transpose < 4):
            w, h = h, w
            # 4-7, the transposition is only done if the input video geometry is portrait and not landscape

    rotdeg = stream_opts.get("rotate", None)
    if rotdeg:
        w, h, rot = utils.get_rotated_shape(w, h, rotdeg)
        vfilters.append(("rotate", rot, w, h, {"c": bg_color}))

    size = stream_opts.get("size", None)
    scale = stream_opts.get("scale", None)
    if size or scale:
        if size:
            w, h = (
                size[1] * w / h if size[0] <= 0 else size[0],
                size[0] * h / w if size[1] <= 0 else size[1],
            )
        else:
            sep = isinstance(scale, Sequence)
            w *= scale[0] if sep else scale
            h *= scale[1] if sep else scale
        if w <= 0 or h <= 0:
            raise Exception

        w = max(int(round(w)), 1)
        h = max(int(round(h)), 1)
        vfilters.append(("scale", w, h))

    opts = {}
    if len(vfilters) > 0:
        opts["vf"] = vfilters
    if out_pix_fmt is not None and (always_copy or out_pix_fmt != info["pix_fmt"]):
        opts["pix_fmt"] = out_pix_fmt

    rate = opts.get("frame_rate", None)
    if rate is not None and rate != info["frame_rate"]:
        opts["r"] = rate

    return (
        opts,
        bg_src,
        (dtype, (h, w, ncomp), rate or info["frame_rate"]) if for_reader else None,
    )


def global_options(
    ffmpeg_args,
    default_opts=None,
    prefix="",
    aliases=None,
    excludes=None,
    **options,
):
    gopts = ffmpeg_args.get("global_options", None)
    if gopts is None:
        ffmpeg_args["global_options"] = gopts = {}

    options = finalize_opts(
        options,
        {"force", "filter_complex"},
        default_opts,
        prefix,
        aliases=aliases,
        excludes=excludes,
    )

    force = options.get("force", None)
    if force is not None:
        if force:
            gopts["y"] = None
        else:
            gopts["n"] = None

    filter_defs = options.get("filter_complex", None)
    if filter_defs is not None:
        gopts["filter_complex"] = (
            filter_defs
            if isinstance(filter_defs, str)
            else filter_utils.compose_graph(*filter_defs[:-1], **filter_defs[-1])
            if isinstance(filter_defs[-1], dict)
            else filter_utils.compose_graph(*filter_defs)
        )

    loglevel = options.get("loglevel", None)
    if loglevel is not None:
        gopts["loglevel"] = loglevel

    return ffmpeg_args


def merge_user_options(ffmpeg_args, type, user_options, file_index=None):

    if isinstance(user_options, str):
        user_options = ffmpeg.parse_options(user_options)

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


def is_forced(ffmpeg_args):
    opts = ffmpeg_args.get("global_options", None)
    return (
        None
        if opts is None
        else True
        if "y" in opts
        else False
        if "n" in opts
        else None
    )


def filters(
    ffmpeg_args,
    url=None,
    prefix="",
    aliases={},
    excludes=None,
    **kwargs,
):
    # TODO Not tested, needs to be expanded
    if url is None:
        opts = ffmpeg_args.get("global_options", None)
        if opts is None:
            ffmpeg_args["global_options"] = opts = {}
    else:
        outopts = add_url(ffmpeg_args, "output", url, {})[1][1]

    opt_names = ("filter_complex",) if url is None else ("af", "vf")

    opts = finalize_opts(
        kwargs,
        opt_names,
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    for k, v in opts.items():
        if not isinstance(v, str):
            if isinstance(v[-1], dict):
                v = filter_utils.compose_graph(*v[:-1], **v[-1])
            else:
                v = filter_utils.compose_graph(*v)
        outopts[k] = v

    return ffmpeg_args


def adjust_audio_range(ffmpeg_args, file_id=0, stream_id=0):
    """estimated range of audio sample indices

    :param ffmpeg_args: argument dict to ffmpeg (possibly modified by this function)
    :type ffmpeg_args: dict
    :param file_id: audio input file index, defaults to 0
    :type file_id: int, optional
    :param stream_id: audio stream index, defaults to 0
    :type stream_id: int, optional
    :return: tuple of first and (exclusive) last sample indices
    :rtype: tuple(int, int)
    """
    url, opts = ffmpeg_args["inputs"][file_id]

    info = probe.audio_streams_basic(url, file_id, ("sample_rate", "nb_samples"))[0]

    i0 = 0
    i1 = info["nb_samples"]

    if opts is None:
        return i0, i1

    fs = (
        get_option(
            ffmpeg_args,
            "input",
            "ar",
            file_id=file_id,
            stream_type="a",
            stream_id=stream_id,
        )
        or info["sample_rate"]
    )

    ss = None if opts is None else utils.parse_time_duration(opts.get("ss", None))
    t = None if opts is None else utils.parse_time_duration(opts.get("t", None))
    to = None if opts is None else utils.parse_time_duration(opts.get("to", None))

    if ss is not None:
        i0 = int(ss * fs)  # starting sample
        ss = i0 / fs
        del opts["ss"]
    else:
        ss = 0.0
    if t is not None:
        i1 = min(int((ss + t) * fs), i1)
        opts["t"] = i1 / fs
    elif to is not None:
        i1 = min(int(to * fs), i1)
        opts["to"] = i1 / fs

    return i0, i1
