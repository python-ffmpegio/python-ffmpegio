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
    return dict(inputs=[], outputs=[], global_options=None)


def add_url(args, type, url, opts=None):
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
        elif aliases and (name := aliases.get(k, None)) is not None:
            opts[name] = v
        elif not prefix or k.startswith(prefix):
            name = k[len(prefix) :]
            if name in opt_names:
                opts[name] = v
    return opts


def find_file_opts(url, type, ffmpeg_args=None):
    """Get file options, create if not available

    :param url: media url
    :type url: str
    :param type: file list type
    :type type: {"inputs", "outputs"}
    :param ffmpeg_args: existing ffmpeg arguments, if not given, new argument set is created
    :type ffmpeg_args: dict, optional
    :return: possibly updated ffmpeg_args and the requested options
    :rtype: dict, dict
    """

    if ffmpeg_args is None:
        ffmpeg_args = empty()

    filelist = ffmpeg_args.get(type, None)
    if filelist is None:
        ffmpeg_args[type] = filelist = []

    nfiles = len(filelist)
    file_id = next((i for i in range(nfiles) if url == filelist[i][0]), nfiles)
    options = filelist[file_id][1] if file_id < nfiles else None
    if options is None:
        options = {}
        if file_id < nfiles:
            filelist[file_id] = (url, options)
        else:
            filelist.append((url, options))
    return ffmpeg_args, options


def input_timing(
    url,
    vstream_id=None,
    astream_id=None,
    ffmpeg_args=None,
    prefix="",
    aliases={},
    excludes=None,
    **kwargs,
):

    if ffmpeg_args is None:
        ffmpeg_args = empty()

    opts = finalize_opts(
        kwargs,
        ("start", "end", "duration", "input_frame_rate", "input_sample_rate", "units"),
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    ffmpeg_args, inopts = find_file_opts(url, "inputs", ffmpeg_args)

    # if start/end/duration are specified
    start = opts.get("start", None)
    end = opts.get("end", None)
    duration = opts.get("duration", None)
    input_frame_rate = opts.get("input_frame_rate", None)
    if input_frame_rate is not None:
        inopts[
            "r" if vstream_id is None else f"r:{utils.spec_stream(vstream_id,'v')}"
        ] = input_frame_rate
    input_sample_rate = opts.get("input_sample_rate", None)
    if input_sample_rate is not None:
        inopts[
            "ar" if astream_id is None else f"ar:{utils.spec_stream(astream_id,'a')}"
        ] = input_sample_rate
    need_units = start is not None or end is not None or duration is not None
    if need_units:
        units = opts.get("units", "seconds")
        fs = (
            1.0
            if need_units or units == "seconds"
            else input_frame_rate
            or probe.video_streams_basic(
                url, index=vstream_id or 0, entries=("frame_rate",)
            )[0]["frame_rate"]
            if units == "frames"
            else input_sample_rate
            or probe.audio_streams_basic(
                url, index=astream_id or 0, entries=("sample_rate",)
            )[0]["sample_rate"]
        )

        if start:
            inopts["ss"] = float(start / fs)
        elif end and duration:
            inopts["ss"] = float((end - duration) / fs)
        if end:
            inopts["to"] = float(end / fs)
        if duration:
            inopts["t"] = float(duration / fs)

    return ffmpeg_args


def video_codec(
    url,
    ffmpeg_args=None,
    prefix="",
    aliases={},
    excludes=None,
    **kwargs,
):

    ffmpeg_args, outopts = find_file_opts(url, "outputs", ffmpeg_args)

    opts = finalize_opts(
        kwargs,
        ("codec", "crf"),
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    if "codec" in opts:
        if (val := opts["codec"]) == "none" or val is None:
            outopts["vn"] = None
        else:
            outopts["vcodec"] = val
    if "crf" in opts:
        outopts["crf"] = opts["crf"]
    return ffmpeg_args


def audio_codec(
    url,
    ffmpeg_args=None,
    prefix="",
    aliases={},
    excludes=None,
    **kwargs,
):
    ffmpeg_args, outopts = find_file_opts(url, "outputs", ffmpeg_args)

    opts = finalize_opts(
        kwargs,
        ("codec"),
        prefix=prefix,
        aliases=aliases,
        excludes=excludes,
    )

    if "codec" in opts:
        if (val := opts["codec"]) == "none" or val is None:
            outopts["an"] = None
        else:
            outopts["acodec"] = val


def filters(
    url=None,
    ffmpeg_args=None,
    prefix="",
    aliases={},
    excludes=None,
    **kwargs,
):
    # TODO Not tested, needs to be expanded
    if url is None:
        if ffmpeg_args is None:
            ffmpeg_args = empty()
        opts = ffmpeg_args.get("global_options", None)
        if opts is None:
            ffmpeg_args["global_options"] = opts = {}
    else:
        ffmpeg_args, outopts = find_file_opts(url, "outputs", ffmpeg_args)

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


def audio_io(
    input,
    *stream_ids,
    file_index=None,
    ffmpeg_args=None,
    prefix="",
    format=None,
    output_url=None,
    aliases={},
    excludes=None,
    **kwargs,
):
    in_file_id, input = (
        add_url(ffmpeg_args, "input", input)
        if isinstance(input, str)
        else add_url(ffmpeg_args, "input", *input)
    )

    ffmpeg_args, out_cfg = find_file_opts(output_url, "outputs", ffmpeg_args)

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
        raise Exception(f'cannot find audio source: {input[0]}')

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
            out_cfg[f"{k}:{id}"] = v

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

    all_info = utils.analyze_audio_input(
        input, entries=("sample_rate", "sample_fmt", "channels")
    )

    print(input,all_info)

    if len(all_info) == 0:
        return None, None

    # make streams list uniform
    nstreams = len(streams)
    streams = (
        [(s, {}) if isinstance(s, int) else s for s in streams]
        if nstreams
        else [(s, {}) for s in range(len(all_info))]
    )

    if len(streams) < 1:
        return None, None

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
                default_opts=file_opts,
            )
            for st in streams
        ]
    )

    return ffmpeg_config, reader_config if for_reader else None


def audio_stream(
    info,
    stream_opts=None,
    *args,
    for_reader=False,
    default_opts={},
):

    opts = (
        finalize_opts(stream_opts, _audio_opts, default_opts)
        if stream_opts
        else default_opts
    )

    rate = opts.get("sample_rate", None)
    fmt = opts.get("sample_fmt", None)
    nch = opts.get("channels", None)

    ffmpeg_config = {}
    if rate is not None and rate != info["sample_rate"]:
        ffmpeg_config["ar"] = rate
    if fmt is not None and fmt != info["sample_fmt"]:
        ffmpeg_config["sample_fmt"] = fmt
    if nch is not None and nch != info["channels"]:
        ffmpeg_config["ac"] = nch

    reader_config = None
    if for_reader:
        codec, dtype = utils.get_audio_format(fmt or info["sample_fmt"])
        ffmpeg_config["codec"] = codec
        reader_config = (dtype, nch or info["channels"], rate or info["sample_rate"])

    return ffmpeg_config, reader_config


def video_io(
    input,
    *stream_ids,
    ffmpeg_args=None,
    prefix="",
    format=None,
    output_url=None,
    aliases={},
    excludes=None,
    **kwargs,
):
    """Create ffmpeg.run() ready arg dict and expected numpy array stream outputs
    :param *input_defs: list of input urls and optional selection of streams
    :type input_defs[]: str or tuple(str, <int|seq>, <dict>)
    :param ffmpeg_args: ffmpeg run arguments to add, defaults to None
    :type ffmpeg_args: dict, optional
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
    :param deinterlace: apply selected deinterlacing filter if available
    :type {'bwdif','estdif','kerndeint','nnedi','w3fdif','yadif','yadif_cuda'}

    Filter Order: crop=>flip=>transpose=>deinterlace=>rotate=>scale


    """

    if not len(stream_ids):
        stream_ids = [0]

    in_file_id, input = (
        add_url(ffmpeg_args, "input", input)
        if isinstance(input, str)
        else add_url(ffmpeg_args, "input", *input)
    )

    ffmpeg_args, out_cfg = find_file_opts(output_url, "outputs", ffmpeg_args)

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

    for i in range(nstreams):

        st_id = stream_ids[i]
        opts = ffmpeg_opts[i]
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
        merge_user_options(ffmpeg_args, "global", {"filter_complex": (*fg, fg_labels)})

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

    all_info = utils.analyze_video_input(
        input, entries=("width", "height", "pix_fmt", "frame_rate")
    )

    if len(all_info) == 0:
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
                default_opts=file_opts,
            )
            for st in streams
        ]
    )

    return ffmpeg_opts, ffmpeg_srcs, reader_cfgs


def video_stream(
    info,
    stream_opts=None,
    *args,
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
    if transpose:
        vfilters.append(("transpose", transpose % 4))

    deint = stream_opts.get("deinterlace", None)
    if deint:
        # fmt: off
        if deint not in ("bwdif", "estdif", "kerndeint", "nnedi", "w3fdif", "yadif", "yadif_cuda"):
            raise Exception("Invalid deinterlacing filter specified.")
        # fmt: on
        vfilters.append(deint)
        h *= 2

    rot = stream_opts.get("rotate", None)
    if rot:
        w, h = utils.get_rotated_shape(w, h, rot)
        vfilters.append(("rotate", rot, w, h, {"c": bg_color}))

    size = stream_opts.get("size", None)
    scale = stream_opts.get("scale", None)
    if size or scale:
        if size:
            if size[0] <= 0:
                size[0] = size[1] * w / h
            elif size[1] <= 0:
                size[1] = size[0] * h / w
            w, h = size
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
    if out_pix_fmt is not None and out_pix_fmt != info["pix_fmt"]:
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
    ffmpeg_args=None,
    default_opts=None,
    prefix="",
    aliases=None,
    excludes=None,
    **options,
):
    gopts = ffmpeg_args.get("global_options", None) if ffmpeg_args else None
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

    return ffmpeg_args


###########################################################################


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


def find_url_id(ffmpeg_args, type, url):
    filelist = ffmpeg_args.get(type + "s", None)
    return filelist and next((i for i, f in enumerate(filelist) if f[0] == url), None)


def get_option(ffmpeg_args, type, name, file_id=None):
    if ffmpeg_args is None:
        return None
    if type.startswith("global"):
        opts = ffmpeg_args.get("global_options", None)
    else:
        filelists = ffmpeg_args.get(f"{type}s", None)
        if not isinstance(file_id, int) or file_id < 0 or file_id >= len(filelists):
            raise Exception("requires a valid `file_id`")
        opts = filelists[file_id][1]
    return opts and opts.get(name, None)
