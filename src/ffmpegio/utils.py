import re, fractions
import numpy as np
from . import caps, probe


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
    fmt_info = caps.pixfmts()[input_pix_fmt]
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
    return int(round(abs(X[0, 0] - X[0, 2]))), int(round(abs(X[1, 1])))


def get_audio_format(fmt):
    """get audio format

    :param fmt: ffmpeg sample_fmt or numpy dtype class
    :type fmt: str or numpy dtype class
    :return: tuple of pcm codec name and (dtype if sample_fmt given or sample_fmt if dtype given)
    :rtype: tuple
    """
    formats = dict(
        u8p=("pcm_u8", np.uint8),
        s16p=("pcm_s16le", np.int16),
        s32p=("pcm_s32le", np.int32),
        s64p=("pcm_s64le", np.int64),
        fltp=("pcm_f32le", np.float32),
        dblp=("pcm_f64le", np.float64),
        u8=("pcm_u8", np.uint8),
        s16=("pcm_s16le", np.int16),
        s32=("pcm_s32le", np.int32),
        s64=("pcm_s64le", np.int64),
        flt=("pcm_f32le", np.float32),
        dbl=("pcm_f64le", np.float64),
    )

    # byteorder = "be" if sys.byteorder == "big" else "le"

    return (
        formats.get(fmt, formats["s16"])
        if isinstance(fmt, str)
        else next(((v[0], k) for k, v in formats.items() if v[1] == fmt))
    )


def array_to_video_input(data, rate=None, stream_id=0, format=None):

    spec = spec_stream(stream_id, "v")

    dtype = data.dtype
    shape = data.shape
    ndim = data.ndim

    if ndim < 2 or ndim > 4:
        raise Exception(f"unknown video data dimension: {shape}")

    nocomp = ndim == 2 or (ndim == 3 and shape[-1] > 4)

    n = 1 if nocomp else shape[-1]
    input = (
        "-",
        (
            opts := {
                f"c:{spec}": "rawvideo",
                f"s:{spec}": f"{shape[-2 + nocomp]}x{shape[-3 + nocomp]}",
            }
        ),
    )

    if format is not None:
        opts["f"] = format

    if rate is not None:
        opts[f"r:{spec}"] = rate

    if dtype == np.uint8:
        opts[f"pix_fmt:{spec}"] = (
            "gray" if n == 1 else "ya8" if n == 2 else "rgb24" if n == 3 else "rgba"
        )
    elif dtype == np.uint16:
        opts[f"pix_fmt:{spec}"] = (
            "gray16le"
            if n == 1
            else "ya16le"
            if n == 2
            else "rgb48le"
            if n == 3
            else "rgba64le"
        )
    elif dtype == np.float32:
        opts[f"pix_fmt:{spec}"] = "grayf32le"
    else:
        raise Exception("Invalid data format")

    return input


def analyze_video_input(input, entries=None):

    if entries is None:
        entries = ("codec_name", "width", "height", "pix_fmt", "frame_rate")

    cfgs = (
        {
            i: v
            for i, v in enumerate(probe.video_streams_basic(input[0], entries=entries))
        }
        if input[0] != "-"
        else {}
    )

    if (opts := input[1]) is not None:
        for k, v in opts.items():
            m = re.match(r"(c|s|pix_fmt|r):v:(\d+)", k)
            if not m:
                continue
            name = m[1]
            st = int(m[2])
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
                    cfg["frame_rate"] = fractions.Fraction(v)
            elif name == "c":
                if "codec_name" in entries:
                    cfg["codec_name"] = v

    # make sure entries are contiguous
    try:
        return [cfgs[i] for i in range(len(cfgs))]
    except:
        raise Exception("input options are either incomplete or invalid")


def array_to_audio_input(data, rate=None, stream_id=0, format=None):

    spec = spec_stream(stream_id, "a")

    acodec, fmt = get_audio_format(data.dtype)

    shape = data.shape
    ndim = data.ndim
    if ndim < 1 or ndim > 2:
        raise Exception("audio data array must be 1d or 2d")
    channels = shape[-1] if ndim > 1 else 1

    input = (
        "-",
        (
            opts := {
                f"c:{spec}": acodec,
                f"sample_fmt:{spec}": fmt,
                f"ac:{spec}": channels,
            }
        ),
    )

    if format is not None:
        opts["f"] = acodec[4:] if format is True else format

    if rate is not None:
        opts[f"ar:{spec}"] = rate

    return input


def analyze_audio_input(input, entries=None):

    if entries is None:
        entries = ("codec_name", "sample_rate", "sample_fmt", "channels")

    cfgs = (
        {
            i: v
            for i, v in enumerate(probe.audio_streams_basic(input[0], entries=entries))
        }
        if input[0] != "-"
        else {}
    )

    if (opts := input[1]) is not None:
        for k, v in opts.items():
            m = re.match(r"(c|ac|sample_fmt|ar):a:(\d+)", k)
            if not m:
                continue
            name = m[1]
            st = int(m[2])
            if st not in cfgs:
                cfgs[st] = {}
            cfg = cfgs[st]
            if name == "ac":
                if "channels" in entries:
                    cfg["channels"] = v
            elif name == "sample_fmt":
                if "sample_fmt" in entries:
                    cfg["sample_fmt"] = v
            elif name == "ar":
                if "sample_rate" in entries:
                    cfg["sample_rate"] = v
            elif name == "c":
                if "codec_name" in entries:
                    cfg["codec_name"] = v

    # make sure entries are contiguous
    try:
        return [cfgs[i] for i in range(len(cfgs))]
    except:
        raise Exception("input options are either incomplete or invalid")
