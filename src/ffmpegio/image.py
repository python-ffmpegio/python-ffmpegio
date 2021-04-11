import numpy as np
from . import ffmpeg, probe, caps


def read(filename, pix_fmt=None, background_color="white", **inopts):
    """read image

    :param filename: audio/video filename
    :type filename: str
    :raises Exception: if FFmpeg fails
    :return: sample rate and audio data matrix (column=time,row=channel)
    :rtype: (float, numpy.ndarray)
    """

    info = probe.video_streams_basic(
        filename, index=0, entries=("width", "height", "pix_fmt")
    )[0]
    width, height, input_pix_fmt = info.values()

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

    if pix_fmt!=input_pix_fmt:
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
    outputs = [("-", outopts := dict(f="rawvideo", pix_fmt=pix_fmt, vframes=1))]
    global_options = {}

    if remove_alpha := not n_in % 2 and n_out % 2:
        # add complex_filter to overlay on
        inputs.append(
            (f"color=c={background_color}:s={width}x{height}", {"f": "lavfi"})
        )
        global_options["filter_complex"] = f"[1:v][0:v]overlay[out]"
        outopts["map"] = "[out]"
    elif add_alpha := n_in % 2 and not n_out % 2:
        inputs.append(
            (f"color=c=white:s={width}x{height}", {"f": "lavfi"})
        )
        global_options["filter_complex"] = f"[0:v][1:v]alphamerge[out]"
        outopts["map"] = "[out]"
    else:
        outopts["map"] = "v:0"
    # if pix_fmt != input_pix_fmt:
    # outopts["vf"] = f"format=pix_fmts={pix_fmt}"

    args = dict(global_options=global_options, inputs=inputs, outputs=outputs)

    print(args)

    stdout = ffmpeg.run_sync(args)
    return np.frombuffer(stdout, dtype=dtype).reshape(height, width, n_out)


def write(filename, data, **outopts):

    dtype = data.dtype
    shape = data.shape
    n = shape[-1] if data.ndim > 2 else 1
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

    args = dict(
        inputs=[
            (
                "-",
                dict(f="rawvideo", pix_fmt=pix_fmt, s=f"{shape[1]}x{shape[0]}"),
            )
        ],
        outputs=[
            (
                filename,
                None,
            )
        ],
    )

    print(args)

    ffmpeg.run_sync(args, input=data.tobytes())
