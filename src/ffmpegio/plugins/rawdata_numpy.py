"""ffmpegio plugin to use `numpy.ndarray` objects for media data I/O"""

from __future__ import annotations
import numpy as np
from pluggy import HookimplMarker
from typing import Tuple

from numpy.typing import ArrayLike

hookimpl = HookimplMarker("ffmpegio")

__all__ = [
    "video_info",
    "audio_info",
    "video_bytes",
    "audio_bytes",
    "bytes_to_video",
    "bytes_to_audio",
]


@hookimpl
def video_info(obj: ArrayLike) -> Tuple[Tuple[int, int, int], str]:
    """get video frame info

    :param obj: video frame data with arbitrary number of frames
    :return shape: shape (height,width,components)
    :return dtype: data type in numpy dtype str expression
    """
    try:
        return obj.shape[-3:] if obj.ndim != 2 else [*obj.shape, 1], obj.dtype.str
    except:
        return None


@hookimpl
def audio_info(obj: ArrayLike) -> Tuple[int, str]:
    """get audio sample info

    :param obj: column-wise audio data with arbitrary number of samples
    :return ac: number of channels
    :return dtype: sample data type in numpy dtype str expression
    """
    try:
        return obj.shape[-1:] if obj.ndim > 1 else [1], obj.dtype.str
    except:
        return None


@hookimpl
def video_bytes(obj: ArrayLike) -> memoryview:
    """return bytes-like object of rawvideo NumPy array

    :param obj: video frame data with arbitrary number of frames
    :return: memoryview of video frames
    """

    try:
        return np.ascontiguousarray(obj).view('b')
    except:
        return None


@hookimpl
def audio_bytes(obj: ArrayLike) -> memoryview:
    """return bytes-like object of rawaudio NumPy array

    :param obj: column-wise audio data with arbitrary number of samples
    :return: memoryview of audio samples
    """

    try:
        return np.ascontiguousarray(obj).view('b')
    except:
        return None


@hookimpl
def bytes_to_video(
    b: bytes, dtype: str, shape: Tuple[int, int, int], squeeze: bool
) -> ArrayLike:
    """convert bytes to rawvideo NumPy array

    :param b: byte data of arbitrary number of video frames
    :param dtype: data type string (e.g., '|u1', '<f4')
    :param size: frame dimension in pixels and number of color components (height, width, components)
    :param squeeze: True to remove all the singular dimensions
    :return: rawvideo frames
    """

    try:
        x = np.frombuffer(b, dtype).reshape(-1, *shape)
        return x.squeeze() if squeeze else x
    except:
        return None


@hookimpl
def bytes_to_audio(b: bytes, dtype: str, shape: Tuple[int], squeeze: bool) -> ArrayLike:
    """convert bytes to rawaudio NumPy array

    :param b: byte data of arbitrary number of video frames
    :param dtype: data type string (e.g., '<s2', '<f4')
    :param shape: number of audio channels
    :param squeeze: True to remove all the singular dimensions
    :return: raw audio samples
    """

    try:
        x = np.frombuffer(b, dtype).reshape(-1, *shape)
        return x.squeeze() if squeeze else x
    except:
        return None
