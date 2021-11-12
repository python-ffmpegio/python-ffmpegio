import re, fractions
import numpy as np
from .. import caps, probe, filter_utils

# fmt:off
_filter_video_srcs = ("allrgb", "allyuv", "buffer", "cellauto", "color",
    "coreimagesrc", "frei0r_src", "gradients", "haldclutsrc", "life", 
    "mandelbrot", "mptestsrc", "nullsrc", "openclsrc", "pal100bars", 
    "pal75bars",  "rgbtestsrc", "sierpinski", "smptebars", "smptehdbars",
    "testsrc", "testsrc2", "yuvtestsrc",
)
_filter_video_snks = ("buffersink", "nullsink")
_filter_audio_srcs = ("abuffer", "aevalsrc", "afirsrc", "anullsrc", 
    "flite", "anoisesrc", "hilbert", "sinc", "sine")
_filter_audio_snks = ("abuffersink", "anullsink")
# fmt:on


def spec_stream(
    index=None,
    type=None,
    program_id=None,
    pid=None,
    tag=None,
    usable=None,
    file_index=None,
):
    """Get stream specifier string

    :param index: Matches the stream with this index. If stream_index is used as
    an additional stream specifier, then it selects stream number stream_index
    from the matching streams. Stream numbering is based on the order of the
    streams as detected by libavformat except when a program ID is also
    specified. In this case it is based on the ordering of the streams in the
    program., defaults to None
    :type index: int, optional
    :param type: One of following: ’v’ or ’V’ for video, ’a’ for audio, ’s’ for
    subtitle, ’d’ for data, and ’t’ for attachments. ’v’ matches all video
    streams, ’V’ only matches video streams which are not attached pictures,
    video thumbnails or cover arts. If additional stream specifier is used, then
    it matches streams which both have this type and match the additional stream
    specifier. Otherwise, it matches all streams of the specified type, defaults
    to None
    :type type: str, optional
    :param program_id: Selects streams which are in the program with this id. If
    additional_stream_specifier is used, then it matches streams which both are
    part of the program and match the additional_stream_specifier, defaults to
    None
    :type program_id: int, optional
    :param pid: stream id given by the container (e.g. PID in MPEG-TS
    container), defaults to None
    :type pid: str, optional
    :param tag: metadata tag key having the specified value. If value is not
    given, matches streams that contain the given tag with any value, defaults
    to None
    :type tag, str or tuple(key,value), optional
    :param usable: streams with usable configuration, the codec must be defined
    and the essential information such as video dimension or audio sample rate
    must be present, defaults to None
    :type usable: bool, optional
    :param file_index: file index to be prepended if specified, defaults to None
    :type file_index: int, optional
    :param filter_output: True to append "out" to stream type, defaults to False
    :type filter_output: bool, optional
    :return: stream specifier string or empty string if all arguments are None
    :rtype: (fractions.Fraction, numpy.ndarray)

    Note matching by metadata will only work properly for input files.

    Note index, pid, tag, and usable are mutually exclusive. Only one of them
    can be specified.

    """

    # nothing specified
    if all(
        [k is None for k in (index, type, program_id, pid, tag, usable, file_index)]
    ):
        return ""

    spec = [] if file_index is None else [str(file_index)]

    if program_id is not None:
        spec.append(f"p:{program_id}")

    if type is not None:
        spec.append(
            dict(video="v", audio="a", subtitle="s", data="d", attachment="t").get(
                type, type
            )
        )

    if sum([k is not None for k in (index, pid, tag, usable)]) > 1:
        raise Exception("Multiple mutually exclusive specifiers are given.")
    if index is not None:
        spec.append(str(index))
    elif pid is not None:
        spec.append(f"#{pid}")
    elif tag is not None:
        spec.append(f"m:{tag}" if isinstance(tag, str) else f"m:{tag[0]}:{tag[1]}")
    elif usable is not None and usable:
        spec.append("u")

    return ":".join(spec)


def get_pixel_config(input_pix_fmt, pix_fmt=None):
    """get best pixel configuration to read video data in specified pixel format

    :param input_pix_fmt: input pixel format
    :type input_pix_fmt: str
    :param pix_fmt: desired output pixel format, defaults to None (auto-select)
    :type pix_fmt: str, optional
    :return: output pix_fmt, number of components, compatible numpy dtype, and whether
             alpha component must be removed
    :rtype: tuple(str,int,numpy.dtype,bool)

    =====  ============  =========  ===================================
    ncomp  dtype         pix_fmt    Description
    =====  ============  =========  ===================================
      1    numpy.uint8   gray       grayscale
      1    numpy.uint16  gray16le   16-bit grayscale
      1    numpy.single  grayf32le  floating-point grayscale
      2    numpy.uint8   ya8        grayscale with alpha channel
      2    numpy.uint16  ya16le     16-bit grayscale with alpha channel
      3    numpy.uint8   rgb24      RGB
      3    numpy.uint16  rgb48le    16-bit RGB
      4    numpy.uint8   rgba       RGB with alpha transparency channel
      4    numpy.uint16  rgba64le   16-bit RGB with alpha channel
    =====  ============  =========  ===================================
    """
    try:
        fmt_info = caps.pixfmts()[input_pix_fmt]
    except:
        raise Exception(
            f"unknown pixel format '{input_pix_fmt}' specified. Run ffmpegio.caps.pixfmts() for supported formats."
        )
    n_in = fmt_info["nb_components"]
    bpp = fmt_info["bits_per_pixel"]

    if pix_fmt is None:
        if n_in == 1:
            pix_fmt = "gray" if bpp <= 8 else "gray16le" if bpp <= 16 else "grayf32le"
        elif n_in == 2:
            pix_fmt = "ya8" if bpp <= 16 else "ya16le"
        elif n_in == 3:
            pix_fmt = "rgb24" if bpp <= 24 else "rgb48le"
        elif n_in == 4:
            pix_fmt = "rgba" if bpp <= 32 else "rgba64le"

    if pix_fmt != input_pix_fmt:
        fmt_info = caps.pixfmts()[pix_fmt]
        n_out = fmt_info["nb_components"]
        bpp = fmt_info["bits_per_pixel"]
    else:
        n_out = n_in

    return (
        pix_fmt,
        n_out,
        np.uint8
        if bpp // n_out <= 8
        else np.uint16
        if bpp // n_out <= 16
        else np.float32,
        not n_in % 2 and n_out % 2,  # True if transparency need to be dropped
    )


def get_rotated_shape(w, h, deg):
    theta = np.deg2rad(deg)
    C = np.cos(theta)
    S = np.sin(theta)
    X = np.matmul([[C, -S], [S, C]], [[w, w, 0.0], [0.0, h, h]])
    return int(round(abs(X[0, 0] - X[0, 2]))), int(round(abs(X[1, 1]))), theta


def get_audio_format(fmt):
    """get audio format

    :param fmt: ffmpeg sample_fmt or numpy dtype class
    :type fmt: str or numpy dtype class
    :return: tuple of pcm codec name and (dtype if sample_fmt given or sample_fmt if dtype given)
    :rtype: tuple
    """
    formats = dict(
        u8=("pcm_u8", np.uint8),
        s16=("pcm_s16le", np.int16),
        s32=("pcm_s32le", np.int32),
        s64=("pcm_s64le", np.int64),
        flt=("pcm_f32le", np.float32),
        dbl=("pcm_f64le", np.float64),
        u8p=("pcm_u8", np.uint8),
        s16p=("pcm_s16le", np.int16),
        s32p=("pcm_s32le", np.int32),
        s64p=("pcm_s64le", np.int64),
        fltp=("pcm_f32le", np.float32),
        dblp=("pcm_f64le", np.float64),
    )

    # byteorder = "be" if sys.byteorder == "big" else "le"
    if isinstance(fmt, str):
        return formats.get(fmt, formats["s16"])
    else:
        try:
            return next(((v[0], k) for k, v in formats.items() if v[1] == fmt))
        except:
            raise Exception(f"incompatible numpy dtype used: {fmt}")


def array_to_video_input(
    rate,
    data=None,
    stream_id=None,
    format=None,
    codec=None,
    pix_fmt=None,
    size=None,
    dtype=None,
):
    """create an stdin input with video stream

    :param rate: input frame rate in frames/second
    :type rate: int, float, or `fractions.Fraction`
    :param data: input data (whole or frame), defaults to None (manual config)
    :type data: `numpy.ndarray`
    :param stream_id: video stream id ('v:#'), defaults None to set the options to be file-wide ('v')
    :type stream_id: int, optional
    :param format: input format, defaults to None (not set). If True, sets to ``rawvideo`` format.
                   Use str to specify a specific container
    :type format: str or bool, optional
    :param codec: video codec, defaults to None to use `rawvideo`.
                   If given, `data` is assumed to be a byte array, containing encoded data. Also,
                   `size` and `pix_fmt` must also be set explicitly
    :type codec: str, optional
    :param pix_fmt: video pixel format, defaults to None. This input is only relevant (and required)
                       if custom `codec` is set.
    :type pix_fmt: str, optional
    :param size: frame size in (width, height), defaults to None. This input is only relevant (and required)
                     if custom `codec` is set.
    :type size: tuple(int,int), optional
    :return: tuple of input url and option dict, base numpy array shape, and dtype
    :rtype: tuple(str, dict), tuple(int,int,int), numpy.dtype
    """

    if data is None:
        if size is None or (dtype is None and pix_fmt is None):
            raise ValueError(
                "size and pix_fmt must be specified to set up video input without sample data block"
            )

        try:
            dtype, n = {
                "gray": (np.uint8, 1),
                "ya8": (np.uint8, 2),
                "rgb24": (np.uint8, 3),
                "rgba": (np.uint8, 4),
                "gray16le": (np.uint16, 1),
                "ya16le": (np.uint16, 2),
                "rgb48le": (np.uint16, 3),
                "rgba64le": (np.uint16, 4),
                "grayf32le": (np.float32, 1),
            }[pix_fmt]
        except:
            raise ValueError("Invalid pix_fmt")
        shape = (*size, n)
    else:
        # if data is given, detect size and pixel_fmt (overwrite user inputs if given)
        dtype = data.dtype
        shape = data.shape
        ndim = data.ndim
        if ndim < 2 or ndim > 4:
            raise Exception(f"unknown video data dimension: {shape}")
        nocomp = ndim == 2 or (ndim == 3 and shape[-1] > 4)
        n = 1 if nocomp else shape[-1]
        if ndim < 2 or ndim > 4:
            raise Exception("video data array must be 2d or 3d or 4d")
        size = (
            shape[2:0:-1]  # frames x rows x columns x ncomponents
            if ndim > 3
            else (
                shape[:0:-1]  # frames x rows x columns
                if nocomp
                else shape[-2::-1]  # rows x columns x ncomponents
            )
            if ndim > 2
            else shape[::-1]  # rows x columns
        )

        if dtype == np.uint8:
            pix_fmt = (
                "gray" if n == 1 else "ya8" if n == 2 else "rgb24" if n == 3 else "rgba"
            )
        elif dtype == np.uint16:
            pix_fmt = (
                "gray16le"
                if n == 1
                else "ya16le"
                if n == 2
                else "rgb48le"
                if n == 3
                else "rgba64le"
            )
        elif dtype == np.float32:
            pix_fmt = "grayf32le"
        else:
            raise Exception("Invalid data format")

    spec = spec_stream(stream_id, "v")

    if codec is None:
        # determine `pix_fmt` and `size` from data
        codec = "rawvideo"
    elif pix_fmt is None or size is None:
        raise Exception(
            "configuring audio input with a custom codec requires `pix_fmt` and `size` to be also specified."
        )

    opts = {
        f"c:{spec}": codec,
        f"s:{spec}": f"{size[0]}x{size[1]}",
        f"r:{spec}": rate,
        f"pix_fmt:{spec}": pix_fmt,
    }
    input = ("-", opts)

    if format is not None:
        if isinstance(format, str):
            opts["f"] = format
        elif format is True:
            opts["f"] = "rawvideo"

    return input, shape, dtype


def array_to_audio_input(
    rate,
    data=None,
    stream_id=None,
    codec=None,
    format=None,
    sample_fmt=None,
    channels=None,
):
    """create an stdin input with audio stream

    :param rate: input sample rate in samples/second
    :type rate: int
    :param data: input data (whole or frame), defaults to None (manual config)
    :type data: `numpy.ndarray`
    :param stream_id: audio stream id ('a:#'), defaults to None to set the options to be file-wide ('a')
    :type stream_id: int, optional
    :param format: input format, defaults to None (not set). If True, sets to appropriate raw audio format.
                   Use str to specify a specific container
    :type format: str or bool, optional
    :param codec: audio codec, defaults to None to pick appropriate PCM codec for the data.
                   If set, `data` is assumed to be a byte array, containing encoded data. Also,
                   `channels` and `sample_fmt` must also be set explicitly
    :type codec: str, optional
    :param sample_fmt: audio sample format, defaults to None. This input is only relevant (and required)
                       if custom `codec` is set.
    :type sample_fmt: str, optional
    :param channels: number of channels, defaults to None. This input is only relevant (and required)
                     if custom `codec` is set.
    :type channels: int, optional
    :return: tuple of input url and option dict
    :rtype: tuple(str, dict)
    """

    spec = spec_stream(stream_id, "a")

    if codec is None:
        codec, sample_fmt = get_audio_format(data.dtype)

        shape = data.shape
        ndim = data.ndim
        if ndim < 1 or ndim > 2:
            raise Exception("audio data array must be 1d or 2d")
        channels = shape[-1] if ndim > 1 else shape[0] if ndim > 0 else 1
    elif sample_fmt is None or channels is None:
        raise Exception(
            "configuring audio input with a custom codec requires `sample_fmt` and `channels` to be also specified."
        )

    opts = {
        f"c:{spec}": codec,
        f"ac:{spec}": channels,
        f"ar:{spec}": rate,
        f"sample_fmt:{spec}": sample_fmt,
    }
    input = ("-", opts)

    if format is not None:
        if isinstance(format, str):
            opts["f"] = format
        elif format is True:
            opts["f"] = codec[4:]

    return input


def analyze_video_input(input, entries=None):
    """analyze video input option entry

    :param input: tuple of url & options (or None)
    :type input: tuple(str,dict or None)
    :param entries: a list of basic video stream info names, defaults to None to select all. See `ffmpegio.probe.video_streams_basic()`
    :type entries: seq of str, optional
    :return: list of stream configuration entries and True if source filter
    :rtype: tuple(list of dict, bool)

    input options, `input[1]`, is expected to be configured with stream specifiers and not with their aliases.
    For example, codec must be specified with 'c:v' rather than 'vcodec'.
    """
    if entries is None:
        entries = ("codec_name", "width", "height", "pix_fmt", "frame_rate")

    option_regex = re.compile(r"(c|s|pix_fmt|r):v(?::(\d+))?")

    def set_cfg(cfgs, file, st, name, v):
        if st is None:
            cfg = file
        else:
            if st not in cfgs:
                cfgs[st] = {}
            cfg = cfgs[st]
        if name == "s":
            mval = re.match(r"(\d+)x(\d+)", v)
            if not mval:
                raise Exception(f"invalid -s input option found: {v}")
            if "width" in entries:
                cfg["width"] = int(mval[1])
            if "height" in entries:
                cfg["height"] = int(mval[2])
        elif name == "pix_fmt":
            if "pix_fmt" in entries:
                cfg["pix_fmt"] = v
        elif name == "r":
            if "frame_rate" in entries:
                cfg["frame_rate"] = v
        elif name == "c":
            if "codec_name" in entries:
                cfg["codec_name"] = v

    return analyze_input(
        probe.video_streams_basic, set_cfg, option_regex, input, entries
    )


def analyze_audio_input(input, entries=None):
    """analyze video input option entry

    :param input: tuple of url & options (or None)
    :type input: tuple(str,dict or None)
    :param entries: a list of basic video stream info names, defaults to None to select all. See `ffmpegio.probe.video_streams_basic()`
    :type entries: seq of str, optional
    :return: list of stream configuration entries and True if source filter
    :rtype: tuple(list of dict, bool)

    input options, `input[1]`, is expected to be configured with stream specifiers
    and not with their aliases. For example, codec must be specified with 'c:v' rather
    than 'vcodec'. Also, all options must have stream specifiers even if they are video
    specific ('pix_fmt:v' instead of 'pix_fmt')
    """
    if entries is None:
        entries = ("codec_name", "sample_rate", "sample_fmt", "channels")

    option_regex = re.compile(r"(c|ac|sample_fmt|ar):a(?::(\d+))?")

    def set_cfg(cfgs, file, st, name, v):
        if st is None:
            cfg = file
        else:
            if st not in cfgs:
                cfgs[st] = {}
            cfg = cfgs[st]
        if name == "ac":
            if "channels" in entries:
                cfg["channels"] = int(v)
        elif name == "sample_fmt":
            if "sample_fmt" in entries:
                cfg["sample_fmt"] = v
        elif name == "ar":
            if "sample_rate" in entries:
                cfg["sample_rate"] = int(v)
        elif name == "c":
            if "codec_name" in entries:
                cfg["codec_name"] = v

    return analyze_input(
        probe.audio_streams_basic, set_cfg, option_regex, input, entries
    )


def analyze_input(streams_basic, set_cfg, option_regex, input, entries):
    """analyze input option entry

    :param streams_basic: probe.audio_streams_basic or probe.video_streams_basic
    :type streams_basic: function
    :param set_cfg: func(cfgs, file, st, name, v) to set new config to output dicts
    :type set_cfg: function
    :param option_regex: compiled regular expression to analyze option key
    :type option_regex: re.Pattern
    :param input: tuple of url & options (or None)
    :type input: tuple(str,dict or None)
    :param entries: a list of basic audio stream info names, defaults to None to select all. See `ffmpegio.probe.audio_streams_basic()`
    :type entries: seq of str, optional
    :return: list of stream configuration entries and True if source filter
    :rtype: tuple(list of dict, bool)

    input options, `input[1]`, is expected to be configured with stream specifiers and not with their aliases.
    For example, codec must be specified with 'c:a' rather than 'acodec'.
    """

    is_stdin = input[0] == "-"

    try:
        filtspec = filter_utils.analyze_filter(input[0], entries)
    except:
        filtspec = None

    cfgs = (
        {0: {}}
        if is_stdin
        else {0: filtspec}
        if filtspec
        else {i: v for i, v in enumerate(streams_basic(input[0], entries=entries))}
    )

    # no target media type in the file
    if not len(cfgs):
        return cfgs, None

    opts = input[1]
    if opts is not None:
        file = {}

        for k, v in opts.items():
            m = option_regex.match(k)
            if not m:
                continue
            name = m[1]
            set_cfg(cfgs, file, int(m[2]) if m[2] else None, name, v)

        for k, v in file.items():
            for cfg in cfgs.values():
                if k not in cfg:
                    cfg[k] = v

    # make sure entries are contiguous
    try:
        return [
            (cfgs[i] if i in cfgs else None) for i in range(max(sorted(cfgs)) + 1)
        ], bool(filtspec)
    except:
        raise Exception("input options are either incomplete or invalid")


def is_filter(url, io_type, stream_type=None):
    """Returns true if url is a filter graph

    :param url: [description]
    :type url: [type]
    :param io_type: [description]
    :type io_type: [type]
    :param stream_type: [description], defaults to None
    :type stream_type: [type], optional
    :return: [description]
    :rtype: [type]
    """
    if not isinstance(url, str):
        url = url[0]
    elif re.match(r"([^=]+)(?:\s*=\s*([\s\S]+))?", url):
        return True

    filter_list = (
        (
            (*_filter_video_srcs, *_filter_audio_srcs)
            if stream_type is None
            else _filter_video_srcs
            if stream_type.startswith("v")
            else _filter_audio_srcs
        )
        if io_type.startswith("i")
        else (
            (*_filter_video_snks, *_filter_audio_snks)
            if stream_type is None
            else _filter_video_snks
            if stream_type.startswith("v")
            else _filter_audio_snks
        )
    )

    return url in filter_list


def parse_video_size(expr):

    m = re.match(r"(\d+)x(\d+)", expr)
    if m:
        return (int(m[1]), int(m[2]))

    return caps.video_size_presets[expr]


def parse_frame_rate(expr):
    try:
        return fractions.Fraction(expr)
    except ValueError:
        return caps.frame_rate_presets[expr]


def parse_color(expr):
    m = re.match(
        r"([^@]+)?(?:@(0x[\da-f]{2}|[0-1]\.[0-9]+))?$",
        expr,
        re.IGNORECASE,
    )
    expr = m[1]
    alpha = m[2] and (int(m[2], 16) if m[2][1] == "x" else float(m[2]))

    m = re.match(
        r"(?:0x|#)?([\da-f]{6})([\da-f]{2})?$",
        expr,
        re.IGNORECASE,
    )
    if m:
        rgb = m[1]
        if m[2] and alpha is None:
            alpha = int(m[2], 16)
    else:
        colors = caps.colors()
        name = next((k for k in colors.keys() if k.lower() == expr.lower()), None)
        if name is None:
            raise Exception("invalid color expression")
        rgb = colors[name][1:]

    return int(rgb[:2], 16), int(rgb[2:4], 16), int(rgb[4:], 16), alpha


def compose_color(r, *args):

    if isinstance(r, str):
        colors = caps.colors()
        name = next((k for k in colors.keys() if k.lower() == r.lower()), None)
        if name is None:
            raise Exception("invalid predefined color name")
        return name
    else:

        def conv(x):
            if isinstance(x, (np.floating, float)):
                x = int(x * 255)
            return f"{x:02X}"

        if len(args) < 4:
            args = (*args, *([255] * (3 - len(args))))

        return "".join((conv(x) for x in (r, *args)))


def layout_to_channels(layout):
    layouts = caps.layouts()["layouts"]
    names = caps.layouts()["channels"].keys()
    if layout in layouts:
        layout = layouts[layout]

    def each_ch(expr):
        if expr in layouts:
            return layout_to_channels(expr)
        elif expr in names:
            return 1
        else:
            m = re.match(r"(?:(\d+)(?:c|C)|(0x[\da-f]+))", expr)
            if m:
                return (
                    int(m[1])
                    if m[1]
                    else sum([(c == "1") for c in tuple(bin(int(m[2], 16))[2:])])
                )
            else:
                raise Exception(f"invalid channel layout expression: {expr}")

    return sum([each_ch(ch) for ch in re.split(r"\+|\|", layout)])


def parse_time_duration(expr):
    """convert time/duration expression to seconds

    if expr is not str, the input is returned without any processing

    :param expr: time/duration expression
    :type expr: str
    :return: time/duration in seconds
    :rtype: float
    """
    if isinstance(expr, str):
        m = re.match(r"(-)?((\d{2})\:)?(\d{2}):(\d{2}(?:\.\d+)?)", expr)
        if m:
            s = int(m[3]) * 60 + float(m[4])
            if m[2]:
                s += 3600 * int(m[2])
            return -s if m[1] else s
        m = re.match(r"(-)?(\d+(?:\.\d+)?)(s|ms|us)?", expr)
        if m:
            s = float(m[2])
            if m[3] == "ms":
                s *= 1e-3
            elif m[3] == "us":
                s *= 1e-6
            return -s if m[1] else s
        raise Exception("invalid time duration")
    return expr
