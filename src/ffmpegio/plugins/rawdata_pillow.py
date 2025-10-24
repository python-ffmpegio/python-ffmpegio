"""ffmpegio plugin to use `Pillow.Image.Image` objects for media data I/O"""

from collections.abc import Sequence
import sys
from math import prod

from PIL import Image, ImageSequence
from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")


@hookimpl
def video_info(
    obj: Image.Image | ImageSequence.Iterator | Sequence[Image.Image],
) -> tuple[tuple[int, int, int], str] | None:

    try:
        return _video_info(obj)
    except:
        # test Sequence[Image.Image]
        try:
            it = iter(obj)
            ans = _video_info(next(it))
        except:
            return None
        else:
            assert all(_video_info(a) == ans for a in it)
            return ans


def _video_info(obj: Image.Image) -> tuple[tuple[int, int, int], str]:
    """get video frame info

    :param obj: matplotlib Figure object
    :type obj: Figure
    :return shape: height x width x nb_color_channels
    :return data_type: Numpy dtype string e.g., "|u1"
    """

    mode = obj.mode
    size = obj.size
    ncomp = dtype = None

    # '1' #(1-bit pixels, black and white, stored with one pixel per byte)
    if mode == "L":  # (8-bit pixels, grayscale)
        ncomp = 1
        dtype = "|u1"
    # 'P' #(8-bit pixels, mapped to any other mode using a color palette)
    elif mode == "RGB":  # (3x8-bit pixels, true color)
        ncomp = 3
        dtype = "|u1"
    elif mode == "RGBA":  # (4x8-bit pixels, true color with transparency mask)
        ncomp = 4
        dtype = "|u1"
    # 'CMYK' #(4x8-bit pixels, color separation)
    # 'YCbCr' #(3x8-bit pixels, color video format) Note that this refers to the JPEG, and not the ITU-R BT.2020, standard
    # 'LAB' # (3x8-bit pixels, the L*a*b color space)
    # 'HSV' #(3x8-bit pixels, Hue, Saturation, Value color space) Hue’s range of 0-255 is a scaled version of 0 degrees <= Hue < 360 degrees
    # 'I' #(32-bit signed integer pixels)
    elif mode == "F":  # (32-bit floating point pixels)
        ncomp = 1
        dtype = "<f4"
    elif mode == "LA":  # (L with alpha)
        ncomp = 2
        dtype = "|u1"
    # 'PA' #(P with alpha)
    # 'RGBX' #(true color with padding)
    # 'RGBa' #(true color with premultiplied alpha)
    # 'La' #(L with premultiplied alpha)
    elif mode == "I;16L":  # (16-bit little endian unsigned integer pixels)
        ncomp = 1
        dtype = ">u2"
    elif mode == "I;16B":  # (16-bit big endian unsigned integer pixels)
        ncomp = 1
        dtype = "<u2"
    elif mode in (
        "I;16",
        "I;16N",
    ):  # (16-bit unsigned integer pixels) | (16-bit native endian unsigned integer pixels)
        ncomp = 1
        dtype = ">u2" if sys.byteorder == "big" else "<u2"
    else:
        raise ValueError(f"Unsupported Pillow Image mode: {mode}")

    return (*size[::-1], ncomp), dtype


@hookimpl
def video_bytes(
    obj: Image.Image | ImageSequence.Iterator | Sequence[Image.Image],
) -> memoryview:
    """return bytes-like object of Pillow Image data

    :param obj: video frame data with arbitrary number of frames
    :type obj: Figure
    :return: memoryview of video frames
    :rtype: memoryview
    """

    try:
        if isinstance(obj, Image.Image):
            return obj.tobytes()
        else:
            return b"".join(o.tobytes() for o in obj)

    except:
        None


@hookimpl
def bytes_to_video(
    b: bytes, dtype: str, shape: tuple[int, int, int], squeeze: bool
) -> list[Image.Image] | Image.Image:
    """convert bytes to Pillow Image

    :param b: byte data of arbitrary number of video frames
    :type b: bytes
    :param dtype: data type string (e.g., '|u1', '<f4')
    :type dtype: str
    :param size: frame dimension in pixels and number of color components (height, width, components)
    :type size: tuple[int, int, int]
    :param squeeze: True to remove all the singular dimensions
    :type squeeze: bool
    :return: rawvideo frames
    :rtype: ArrayLike
    """

    try:
        size = shape[1::-1]
        ncomp = shape[-1]
        if ncomp == 1 and dtype == "|u1":
            mode = "L"
        elif ncomp == 3 and dtype == "|u1":
            mode = "RGB"  # (3x8-bit pixels, true color)
        elif ncomp == 4 and dtype == "|u1":
            mode = "RGBA"  # (4x8-bit pixels, true color with transparency mask)
        elif ncomp == 1 and dtype == "<f4":
            mode = "F"  # (32-bit floating point pixels)
        elif ncomp == 2 and dtype == "|u1":
            mode = "LA"  # (L with alpha)
        elif ncomp == 1 and dtype == ">u2":
            mode = "I;16L"  # (16-bit little endian unsigned integer pixels)
        elif ncomp == 1 and dtype == "<u2":
            mode = "I;16B"  # (16-bit big endian unsigned integer pixels)
        else:
            raise ValueError(
                f"Cannot resolve {ncomp=} and {dtype=} to a Pillow Image mode"
            )

        ntotal = len(b)
        nframe = prod(shape) * int(dtype[-1])

        x = [
            Image.frombuffer(mode, size, b[i0 : i0 + nframe])
            for i0 in range(0, ntotal, nframe)
        ]

        return x[0] if squeeze and len(x) == 1 else x
    except:
        return None
