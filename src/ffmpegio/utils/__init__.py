import re, fractions
import numpy as np
from .. import caps

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


def parse_spec_stream(spec):
    if isinstance(spec, str):
        out = {}
        while len(spec):
            if spec.startswith("p:"):
                _, v, *r = spec.split(":", 2)
                out["program_id"] = int(v)
                spec = r[0] if len(r) else ""
            elif spec[0] in "vVadt" and (len(spec) == 1 or spec[1] == ":"):
                out["type"], *r = spec.split(":", 1)
                spec = r[0] if len(r) else ""
            else:
                break
        if not spec:
            return out

        try:
            out["index"] = int(spec)
        except:
            m = re.match(r"#(\d+)$|i\:(\d+)$|m\:(.+?)(?:\:(.+?))?$|(u)$", spec)
            if not m:
                raise ValueError("Invalid stream specifier.")

            if m[1] is not None or m[2] is not None:
                out["pid"] = int(m[1] if m[2] is None else m[2])
            elif m[3] is not None:
                out["tag"] = m[3] if m[4] is None else (m[3], m[4])
            elif m[5]:
                out["usable"] = True
        return out
    else:
        return {"index": int(spec)}


def spec_stream(
    index=None,
    type=None,
    program_id=None,
    pid=None,
    tag=None,
    usable=None,
    file_index=None,
    no_join=False,
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
    :param no_join: True to return list of stream specifier elements, defaults to False
    :type no_join: bool, optional
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
        return [] if no_join else ""

    spec = [] if file_index is None else [str(file_index)]

    if type is not None:
        spec.append(
            dict(video="v", audio="a", subtitle="s", data="d", attachment="t").get(
                type, type
            )
        )

    if program_id is not None:
        spec.append(f"p:{program_id}")

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

    return spec if no_join else ":".join(spec)


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
        fmt_info = caps.pix_fmts()[input_pix_fmt]
    except:
        raise Exception(
            f"unknown pixel format '{input_pix_fmt}' specified. Run ffmpegio.caps.pix_fmts() for supported formats."
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
        fmt_info = caps.pix_fmts()[pix_fmt]
        n_out = fmt_info["nb_components"]
        bpp = fmt_info["bits_per_pixel"]
    else:
        n_out = n_in

    is_bytestream = not (
        pix_fmt.startswith("gray")
        or pix_fmt.startswith("ya")
        or pix_fmt.startswith("rgb")
    )

    return (
        pix_fmt,
        None if is_bytestream else n_out,
        np.bytes
        if is_bytestream
        else np.uint8
        if bpp // n_out <= 8
        else np.uint16
        if bpp // n_out <= 16
        else np.float32,
        not n_in % 2 and n_out % 2,  # True if transparency need to be dropped
    )


def get_video_format(fmt):
    """get video pixel format

    :param fmt: ffmpeg pix_fmt or numpy dtype class
    :type fmt: str or numpy dtype class
    :param return_format: True to return raw audio format name instead of pcm codec name
    :type return_format: bool
    :return: tuple of dtype, number of components, and True if has alpha channel
    :rtype: tuple
    """
    try:
        return dict(
            gray=(np.uint8, 1, False),
            gray16le=(np.uint16, 1, False),
            grayf32le=(np.float32, 1, False),
            ya8=(np.uint8, 2, True),
            ya16le=(np.uint16, 2, True),
            rgb24=(np.uint8, 3, False),
            rgb48le=(np.uint16, 3, False),
            rgba=(np.uint8, 4, True),
            rgba64le=(np.dtype("f2"), 4, True),
        )[fmt]
    except:
        raise ValueError(f"{fmt} is not a valid grayscale/rgb pix_fmt")


def guess_video_format(data=None):
    """get video format

    :param data: data array or a tuple of non-temporal shape and dtype of the data
    :type data: numpy.ndarray or (numpy.dtype, seq of ints)
    :return: tuple of size and pix_fmt
    :rtype: tuple(tuple(int,int),str)

    ```
        X = np.ones((100,480,640,3),np.uint8)
        size, pix_fmt = guess_video_format(X)
        # => size=(640,480), pix_fmt='rgb24'

        # the same result can be obtained by
        size, pix_fmt = guess_video_format((X.shape,X.dtype))
    """

    try:
        dtype = np.dtype(data.dtype)
        shape = data.shape
        ndim = data.ndim
    except:
        try:
            shape, dtype = data
            ndim = len(shape)
            dtype = np.dtype(dtype)
        except:
            raise ValueError(
                "invalid input argument: must be either numpy.array or (shape, dtype) sequence"
            )

    if ndim < 2 or ndim > 4:
        raise ValueError(
            f"invalid video data dimension: data shape must be must be 2d, 3d or 4d"
        )

    has_comp = ndim != 2 and (ndim != 3 or shape[-1] < 5)
    size = shape[-2:-4:-1] if has_comp else shape[:-3:-1]
    ncomp = shape[-1] if has_comp else 1

    try:
        pix_fmt = {
            np.dtype(np.uint8): {1: "gray", 2: "ya8", 3: "rgb24", 4: "rgba"},
            np.dtype(np.uint16): {
                1: "gray16le",
                2: "ya16le",
                3: "rgb48le",
                4: "rgba64le",
            },
            np.dtype(np.float32): {1: "grayf32le"},
        }[dtype][ncomp]
    except Exception as e:
        print(e)
        raise ValueError(
            f"dtype ({dtype}) and guessed number of components ({ncomp}) do not yield a pix_fmt."
        )

    return size, pix_fmt


def get_rotated_shape(w, h, deg):
    theta = np.deg2rad(deg)
    C = np.cos(theta)
    S = np.sin(theta)
    X = np.matmul([[C, -S], [S, C]], [[w, w, 0.0], [0.0, h, h]])
    return int(round(abs(X[0, 0] - X[0, 2]))), int(round(abs(X[1, 1]))), theta


def get_audio_format(fmt, return_format=False):
    """get audio format

    :param fmt: ffmpeg sample_fmt or numpy dtype class
    :type fmt: str or numpy dtype class
    :param return_format: True to return raw audio format name instead of pcm codec name
    :type return_format: bool
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
        out = formats.get(fmt, formats["s16"])
        return (out[0][4:], out[1]) if return_format else out

    else:
        try:
            return next(((v[0], k) for k, v in formats.items() if v[1] == fmt))
        except:
            raise ValueError(f"incompatible numpy dtype used: {fmt}")


def array_to_video_input(
    rate,
    data=None,
    shape=None,
    dtype=None,
    stream_id=None,
    partial_ok=False,
    **opts,
):
    """create an stdin input with video stream

    :param rate: input frame rate in frames/second
    :type rate: int, float, or `fractions.Fraction`
    :param data: input data (whole or frame), defaults to None (manual config)
    :type data: `numpy.ndarray`
    :param stream_id: video stream id ('v:#'), defaults None to set the options to be file-wide ('v')
    :type stream_id: int, optional
    :param partial_ok: True to allow only setting known options, default to False
    :type partial_ok: bool, optional
    :param **opts: input options
    :type **opts: dict
    :return: tuple of input url and option dict
    :rtype: tuple(str, dict)
    """

    spec = "" if stream_id is None else ":" + spec_stream(stream_id, "v")

    if data is not None:
        s, pix_fmt = guess_video_format(data)
    else:
        s = pix_fmt = ncomp = None
        if dtype is None:
            pix_fmt = opts.get(f"pix_fmt{spec}", opts.get("pix_fmt", None))
            if pix_fmt:
                dtype, ncomp, _ = get_video_format(pix_fmt)

        if shape is None:
            s = opts.get(f"s{spec}", opts.get("s", None))
            if ncomp and s:
                shape = (*s[::-1], ncomp)
        elif ncomp and ((shape[-1] != ncomp) or (ncomp == 1 and len(shape) < 4)):
            raise ValueError("pix_fmt and shape are not compatible.")
        if dtype is not None and shape is not None:
            s, pix_fmt = guess_video_format((shape, dtype))

    if not partial_ok and (s is None or pix_fmt is None):
        raise ValueError(
            f"data or a valid combination of (shape, dtype, pix_fmt, s) must be specified"
        )

    inopts = {"f": "rawvideo"}
    for k, v in zip(
        (f"c{spec or ':v'}", f"s{spec}", f"r{spec}", f"pix_fmt{spec}"),
        ("rawvideo", s, rate, pix_fmt),
    ):
        inopts[k] = v

    return ("-", {**inopts, **opts})


def array_to_audio_input(
    rate,
    data=None,
    stream_id=None,
    sample_fmt=None,
    ac=None,
    partial_ok=False,
    **opts,
):
    """create an stdin input with audio stream

    :param rate: input sample rate in samples/second
    :type rate: int
    :param data: input data (whole or frame), defaults to None (manual config)
    :type data: `numpy.ndarray`
    :param stream_id: audio stream id ('a:#'), defaults to None to set the options to be file-wide ('a')
    :type stream_id: int, optional
    :param sample_fmt: audio sample format, defaults to None. This input is only relevant (and required)
                       if custom `codec` is set.
    :type sample_fmt: str, optional
    :param ac: number of ac, defaults to None. This input is only relevant (and required)
                     if custom `codec` is set.
    :type ac: int, optional
    :param partial_ok: True to allow only setting known options, default to False
    :type partial_ok: bool, optional
    :return: tuple of input url and option dict
    :rtype: tuple(str, dict)
    """

    if data is not None:
        dtype = data.dtype
        codec, sample_fmt = get_audio_format(dtype)
        shape = data.shape
        ndim = data.ndim
        if ndim < 1 or ndim > 2:
            raise Exception("audio data array must be 1d or 2d")
        ac = shape[-1] if ndim > 1 else 1
    elif sample_fmt is not None:
        codec, dtype = get_audio_format(sample_fmt)
    else:
        codec = None
        dtype = None

    f = codec[4:] if codec else None

    spec = "" if stream_id is None else ":" + spec_stream(stream_id, "a")

    for k, v in zip(
        (f"c{spec or ':a'}", f"ac{spec}", f"ar{spec}", f"sample_fmt{spec}", "f"),
        (codec, ac, rate, sample_fmt, f),
    ):
        if v is not None:
            opts[k] = v
        elif not partial_ok:
            raise ValueError(f"audio input option `{k}` could not be deduced")

    return ("-", opts), ac, dtype


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


def pop_extra_options(options, suffix):
    n = len(suffix)
    return {
        k[:-n]: options.pop(k)
        for k in [k for k in options.keys() if k.endswith(suffix)]
    }


def bytes_to_ndarray(
    b,
    shape=None,
    dtype=None,
):
    """Convert bytes to numpy.ndarray.

    :param b: raw data to be converted to array
    :type b: bytes-like object, optional
    :param block: True to block if queue is full
    :type block: bool, optional
    :param timeout: timeout in seconds if blocked
    :type timeout: float, optional
    :param shape: sizes of higher dimensions of the output array, default:
                    None (1d array). The first dimension is set by size parameter.
    :type shape: int, optional
    :param dtype: numpy.ndarray data type
    :type dtype: data-type, optional
    :return: bytes read
    :rtype: numpy.ndarray

    As a convenience, if size is unspecified or -1, all bytes until EOF are
    returned. Otherwise, only one system call is ever made. Fewer than size
    bytes may be returned if the operating system call returns fewer than
    size bytes.

    If 0 bytes are returned, and size was not 0, this indicates end of file.
    If the object is in non-blocking mode and no bytes are available, None
    is returned.

    The default implementation defers to readall() and readinto().
    """

    shape = np.atleast_1d(shape) if bool(shape) else ()
    nblk = np.prod(shape, dtype=int)
    size = len(b) // (nblk * np.dtype(dtype).itemsize)
    return np.frombuffer(b, dtype, size * nblk).reshape(-1, *shape)


def get_itemsize(shape, dtype):
    return np.prod(shape, dtype=int) * np.dtype(dtype).itemsize
