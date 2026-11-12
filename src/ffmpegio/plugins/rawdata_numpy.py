"""Read/write Numpy :py:class:`ndarray <numpy.ndarray>` objects (video & audio)"""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pluggy import HookimplMarker

from .._typing import DTypeString, ShapeTuple

logger = logging.getLogger("ffmpegio.plugins")

hookimpl = HookimplMarker("ffmpegio")

__all__ = [
    "audio_bytes",
    "audio_info",
    "audio_samples",
    "bytes_to_audio",
    "bytes_to_video",
    "video_bytes",
    "video_frames",
    "video_info",
]


@hookimpl
def video_info(obj: ArrayLike) -> tuple[ShapeTuple, DTypeString]:
    """get video frame info

    :param obj: video frame data with arbitrary number of frames
    :return shape: shape (height,width,components)
    :return dtype: data type in numpy dtype str expression
    """
    try:
        memoryview(obj)  # Will raise TypeError if not supported
    except TypeError:
        logger.info("rawdata_numpy.video_info::not a memoryview object")
        return None  # No buffer protocol

    a = np.asarray(obj)
    if a.ndim == 2:
        shape = (*a.shape, 1)
    elif a.ndim == 3 and a.shape[-1] > 4:
        shape = (*a.shape[1:], 1)
    else:
        shape = a.shape[-3:]

    if len(shape) not in (2, 3, 4) or a.dtype.char not in "BHf":
        logger.info("rawdata_numpy.video_info::incompatible memoryview shape or dtype")
        return None

    return shape, a.dtype.str


@hookimpl
def audio_info(obj: ArrayLike) -> tuple[ShapeTuple, DTypeString]:
    """get audio sample info

    :param obj: column-wise audio data with arbitrary number of samples
    :return ac: number of channels
    :return dtype: sample data type in numpy dtype str expression
    """

    try:
        memoryview(obj)  # Will raise TypeError if not supported
    except TypeError:
        logger.info("rawdata_numpy.video_info::not a memoryview object")
        return None  # No buffer protocol

    a = np.asarray(obj)

    if len(a.shape) not in (1, 2) or a.dtype.char not in "Bhifd":
        logger.info("rawdata_numpy.video_info::incompatible memoryview shape or dtype")
        return None

    return a.shape[-1:] if a.ndim > 1 else [1], a.dtype.str


@hookimpl
def video_frames(obj: ArrayLike) -> int:
    """get number of video frames in obj

    :param obj: object containing video frame data with arbitrary number of frames
    :return: number of video frames in obj
    Note: if blob is squeezed, the returned value may not be accurate.
    """

    try:
        a = np.asarray(obj)
        shape = a.shape
        ndim = a.ndim
        if ndim > 3:
            return shape[0]
        elif ndim < 3:
            return 1
        else:
            return shape[0] if shape[-1] > 4 else 1
    except:
        return None


@hookimpl
def audio_samples(obj: ArrayLike) -> int:
    """get audio sample info

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :return: number of samples in obj

    Note: assumes a blob of audio samples always consists of more one time sample.
    """

    try:
        return np.asarray(obj).shape[0]
    except:
        return None


@hookimpl
def video_bytes(obj: ArrayLike) -> memoryview:
    """return bytes-like object of rawvideo NumPy array

    :param obj: video frame data with arbitrary number of frames
    :return: memoryview of video frames
    """

    try:
        return np.ascontiguousarray(obj).reshape(-1).view("b")
    except:
        return None


@hookimpl
def audio_bytes(obj: ArrayLike) -> memoryview:
    """return bytes-like object of rawaudio NumPy array

    :param obj: column-wise audio data with arbitrary number of samples
    :return: memoryview of audio samples
    """

    try:
        return np.ascontiguousarray(obj).reshape(-1).view("b")
    except:
        return None


@hookimpl
def bytes_to_video(
    b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
) -> NDArray:
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
def bytes_to_audio(
    b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
) -> NDArray:
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


@hookimpl
def is_empty(obj: NDArray) -> bool:
    """:code:`True` if data blob object has no data

    :param obj: object containing media data
    """
    return obj.size == 0
