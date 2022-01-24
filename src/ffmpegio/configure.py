import re, logging
import numpy as np

from . import utils
from .utils.filter import video_basic_filter


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


def has_filtergraph(args, type, file_id=None, stream_id=None):
    """True if FFmpeg arguments specify a filter graph

    :param args: FFmpeg argument dict
    :type args: dict
    :param type: filter type
    :type type: 'video' or 'audio'
    :param file_id: specify output file id (ignored if type=='complex'), defaults to None (or 0)
    :type file_id: int, optional
    :param stream_id: stream, defaults to None
    :type stream_id: int, optional
    :return: True if filter graph is specified
    :rtype: bool
    """
    try:
        if (
            "filter_complex" in args["global_options"]
            or "lavfi" in args["global_options"]
        ):
            return True
    except:
        pass  # no global_options defined

    try:
        opts = args["outputs"][file_id or 0][1]
        spec = utils.spec_stream(stream_id, type, no_join=True)
        spec[0] = f"filter:{spec[0]}"
        for i in range(1, len(spec)):
            spec[i] = f"{spec[i-1]}:{spec[i]}"
        onames = (*spec[::-1], f"{spec[0][-1]}f")
        return any((o in opts for o in onames))
    except:
        return False  # no output options defined


def finalize_video_read_opts(
    args, pix_fmt_in=None, s_in=None, r_in=None, ofile=0, ifile=0
):
    inopts = args["inputs"][ifile][1] or {}
    outopts = args["outputs"][ofile][1]

    if outopts is None:
        outopts = {}
        args["outputs"][ofile] = (args["outputs"][ofile][0], outopts)

    # pixel format must be specified
    pix_fmt = outopts.get("pix_fmt", None)
    remove_alpha = False
    if pix_fmt is None:
        # deduce output pixel format from the input pixel format
        pix_fmt_in = inopts.get("pix_fmt", pix_fmt_in)
        try:
            outopts["pix_fmt"], ncomp, dtype, _ = utils.get_pixel_config(pix_fmt_in)
        except:
            ncomp = dtype = None
    else:
        # make sure assigned pix_fmt is valid
        if pix_fmt_in is None:
            try:
                dtype, ncomp, _ = utils.get_video_format(pix_fmt)
            except:
                ncomp = dtype = None
            remove_alpha = False
        else:
            _, ncomp, dtype, remove_alpha = utils.get_pixel_config(pix_fmt_in, pix_fmt)

    # set up basic video filter if specified
    fopts = {
        name: outopts.pop(name)
        for name in ("fill_color", "crop", "flip", "transpose", "square_pixels")
        if name in outopts
    }

    # check if output needs to be scaled
    scale = outopts.get("s", None)
    do_scale = scale is not None
    if do_scale:
        try:
            m = re.match(r"(\d+)x(\d+)", scale)
            scale = (int(m[1]), int(m[2]))
        except:
            pass
        try:
            do_scale = len(scale) > 2 or [scale[0] <= 0 or scale[1] <= 0]
        except:
            do_scale = False

    nfo = len(fopts)
    if (nfo and (nfo > 1 or "fill_color" not in fopts)) or remove_alpha or do_scale:
        if do_scale:
            fopts["scale"] = scale
            del outopts["s"]

        if remove_alpha:
            fopts["remove_alpha"] = True

        if "vf" in outopts:
            raise ValueError(
                f"cannot specify `vf` and video basic filter options {tuple(fopts.keys())}"
            )

        outopts["vf"] = video_basic_filter(**fopts)

    outopts["f"] = "rawvideo"

    # if no filter and video shape and rate are known, all known
    r = shape = None
    if not has_filtergraph(args, "video", ofile) and ncomp is not None:
        r = outopts.get("r", inopts.get("r", r_in))

        s = outopts.get("s", inopts.get("s", s_in))
        if s is not None:
            if isinstance(s, str):
                m = re.match(r"(\d+)x(\d+)", s)
                s = [int(m[1]), int(m[2])]
            shape = (*s[::-1], ncomp)

    return dtype, shape, r


def finalize_audio_read_opts(
    args, sample_fmt_in=None, ac_in=None, ar_in=None, ofile=0, ifile=0
):
    inopts = args["inputs"][ifile][1] or {}
    outopts = args["outputs"][ofile][1]
    has_filter = has_filtergraph(args, "audio", ofile)

    if outopts is None:
        outopts = {}
        args["outputs"][ofile] = (args["outputs"][ofile][0], outopts)

    # pixel format must be specified
    sample_fmt = outopts.get("sample_fmt", None)
    if sample_fmt is None:
        # get pixel format from input
        sample_fmt = inopts.get("sample_fmt", sample_fmt_in)
        if sample_fmt[-1] == "p":
            # planar format is not supported
            sample_fmt = sample_fmt[:-1]
        outopts["sample_fmt"] = sample_fmt  # set the format

    # set output format and codec
    acodec, dtype = utils.get_audio_format(sample_fmt)
    outopts["c:a"] = acodec
    outopts["f"] = acodec[4:]

    ac = ar = None
    if not has_filter:
        ac = outopts.get("ac", inopts.get("ac", ac_in))
        ar = outopts.get("ar", inopts.get("ar", ar_in))

    return sample_fmt, dtype, ac, ar


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
        dtype, ncomp, _ = utils.get_video_format(opts["pix_fmt"])
        shape = [*opts["s"][::-1], ncomp]
    except:
        raise ValueError(f"{type} options must specify both `s` and `pix_fmt` options")

    return shape, dtype


def move_global_options(args):
    """move global options from the output options dicts

    :param args: FFmpeg arguments
    :type args: dict
    :returns: FFmpeg arguments (the same object as the input)
    :rtype: dict
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


def clear_loglevel(args):
    """clear global loglevel option

    :param args: FFmpeg argument dict
    :type args: dict


    """
    try:
        del args["global_options"]["loglevel"]
        logging.warn("loglevel option is cleared by ffmpegio")
    except:
        pass
