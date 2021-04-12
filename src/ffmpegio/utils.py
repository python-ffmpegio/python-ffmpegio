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


def config_image_reader(filename, index=0, **kwargs):
    info = probe.video_streams_basic(
        filename, index=index, entries=("width", "height", "pix_fmt")
    )[0]
    width, height, input_pix_fmt = info.values()

    fmt_info = caps.pixfmts()[input_pix_fmt]
    n_in = fmt_info["nb_components"]
    bpp = fmt_info["bits_per_pixel"]
    if (pix_fmt := kwargs.get("pix_fmt", None)) is None:
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
    dtype = (
        np.uint8
        if bpp // n_out <= 8
        else np.uint16
        if bpp // n_out <= 16
        else np.float32
    )

    inputs = [(filename, None)]
    outputs = [("-", outopts := dict(f="rawvideo", pix_fmt=pix_fmt))]
    global_options = {}

    if not n_in % 2 and n_out % 2:
        background_color = kwargs.get("background_color", "white")
        # add complex_filter to overlay on
        inputs.append(
            (f"color=c={background_color}:s={width}x{height}", {"f": "lavfi"})
        )
        global_options["filter_complex"] = f"[1:v][0:v:{index}]overlay[out]"
        outopts["map"] = "[out]"
    else:
        outopts["map"] = f"v:{index}"

    return inputs, outputs, global_options, dtype, (height, width, n_out)


def config_image_writer(filename, dtype, shape, **options):
    n = shape[-1] if len(shape) > 2 else 1
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

    inputs = [
        (
            "-",
            dict(f="rawvideo", pix_fmt=pix_fmt, s=f"{shape[1]}x{shape[0]}"),
        )
    ]
    outputs = [
        (
            filename,
            {},
        )
    ]

    return inputs, outputs
