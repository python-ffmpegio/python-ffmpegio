import numpy as np

from . import caps, probe


def config_image_reader(filename, index=0, **kwargs):
    info = probe.video_streams_basic(
        filename, index=index, entries=("width", "height", "pix_fmt")
    )[0]
    print(info)
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
