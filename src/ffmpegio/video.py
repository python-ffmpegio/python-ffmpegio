import ffmpeg
import numpy as np

from . import caps

def get_codec_info(inputFileName, process=False):
    """get the info dict of the first video stream

    inputFileName (str): media file path
    process (bool): (option, default=False) True to convert fractional property to number
    """
    info = next(
        st
        for st in ffmpeg.probe(inputFileName)["streams"]
        if st["codec_type"] == "video"
    )

    if process:
        for prop in (
            "codec_time_base",
            "nal_length_size",
            "r_frame_rate",
            "avg_frame_rate",
            "time_base",
            "start_time",
            "duration",
            "bit_rate",
            "bits_per_raw_sample",
            "nb_frames",
        ):
            if prop in info:
                info[prop] = eval(info[prop])
    return info


def get_framerate(inputFileName):
    stream = get_codec_info(inputFileName)
    return eval(stream.get("avg_frame_rate", stream.get("r_frame_rate", None)))


# supported pix_fmts
_pix_fmt_list = (
    "0bgr",
    "0rgb",
    "abgr",
    "argb",
    "bgr0",
    "bgr24",
    "bgra",
    "gbrp",
    "gray",
    "pal8",
    "rgb0",
    "rgb24",
    "rgba",
    "ya8",
)
_pix_fmtu16_list = ("bgr48", "bgra64", "gray16", "rgb48", "rgba64", "ya16")
_pix_fmtf32_list = ("grayf32",)
byteorder = "be" if sys.byteorder == "big" else "le"


def get_frame_info(inputFileName, **kwargs):
    """get information on retrieved frames

    Parameters:
        inputFileName (str): input media file path
        fmt (str): output frame format (default: rgb24, see _pix_fmt_list for options)
        vframes (int): number of frames to retrieve OR
        tframes (float): duration of frames to retireve at a time
        height (int): (optional) frame height
        width (int): (optional) frame width
        r (float): (optional) video framerate

    Returns:
        tuple (dtype, shape):
            dtype (str): frame data type
            shape (int[]): tuple of shape

    """

    fmt = kwargs.get("fmt", "rgb24")
    h = kwargs.get("height", 0)
    w = kwargs.get("width", 0)
    pack = kwargs.get("pack", True)

    vframes = kwargs.get("vframes", 0)
    tframes = kwargs.get("tframes", 0)
    r = kwargs.get("r", 0)
    need_tframes = kwargs.get("need_tframes", False)
    need_r = ((not vframes and tframes) or (need_tframes and not tframes)) and not r

    if h <= 0 or w <= 0 or need_r:
        info = get_codec_info(inputFileName)
        if h <= 0:
            h = int(info["height"])
        if w <= 0:
            w = int(info["width"])
        if need_r:
            r = eval(info.get("avg_frame_rate", info.get("r_frame_rate", None)))

    if not vframes:
        vframes = round(tframes * r) if tframes else 1
    if need_tframes and not tframes:
        tframes = vframes / r

    (pix_fmt, dtype) = next(
        ((f, np.uint8) for f in _pix_fmt_list if f == fmt),
        next(
            (
                ("%s%s" % (f, byteorder), np.uint16)
                for f in _pix_fmtu16_list
                if f == fmt
            ),
            next(
                (
                    ("%s%s" % (f, byteorder), np.float32)
                    for f in _pix_fmtf32_list
                    if f == fmt
                ),
                None,
            ),
        ),
    )

    nch = caps.pixfmts()[pix_fmt]["nbComponents"]

    shape = (
        (tuple() if pack and vframes == 1 else (vframes,))
        + (h, w)
        + (tuple() if pack and nch == 1 else (nch,))
    )

    return (dtype, shape, tframes) if need_tframes else (dtype, shape)
