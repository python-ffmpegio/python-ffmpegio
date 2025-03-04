from __future__ import annotations

from .._utils import get_samplesize
from pluggy import HookimplMarker
from typing import Tuple, TypedDict

__all__ = [
    "BytesRawDataBlob",
    "video_info",
    "audio_info",
    "video_bytes",
    "audio_bytes",
    "bytes_to_video",
    "bytes_to_audio",
]

hookimpl = HookimplMarker("ffmpegio")


class BytesRawDataBlob(TypedDict):
    """raw data blob in bytes"""

    buffer: bytes
    """data buffer"""

    dtype: str
    """numpy-style data type string"""

    shape: Tuple[int, int, int]
    """data shape"""


@hookimpl
def video_info(obj: BytesRawDataBlob) -> Tuple[Tuple[int, int, int], str]:
    """get video frame info

    :param obj: dict containing video frame data with arbitrary number of frames
    :return shape: shape (height,width,components)
    :return dtype: data type in numpy dtype str expression
    """

    try:
        return obj["shape"][-3:], obj["dtype"]
    except:
        return None


@hookimpl
def audio_info(obj: BytesRawDataBlob) -> Tuple[int, str]:
    """get audio sample info

    :param obj: dict containing audio data (with interleaving channels) with arbitrary number of samples
    :return ac: number of channels
    :return dtype: sample data type in numpy dtype str expression
    """
    try:
        return obj["shape"][-1:], obj["dtype"]
    except:
        return None


@hookimpl
def video_bytes(obj: BytesRawDataBlob) -> memoryview:
    """return bytes-like object of packed video pixels, associated with `video_info()`

    :param obj: dict containing video frame data with arbitrary number of frames
    :return: packed bytes of video frames
    """

    try:
        return obj["buffer"]
    except:
        return None


@hookimpl
def audio_bytes(obj: BytesRawDataBlob) -> memoryview:
    """return bytes-like object of packed audio samples

    :param obj: dict containing audio data (with interleaving channels) with arbitrary number of samples
    :return: packed bytes of audio samples
    """

    try:
        return obj["buffer"]
    except:
        return None


@hookimpl
def bytes_to_video(
    b: bytes, dtype: str, shape: Tuple[int, int, int], squeeze: bool
) -> BytesRawDataBlob:
    """convert bytes to rawvideo object

    :param b: byte data of arbitrary number of video frames
    :param dtype: data type numpy dtype string (e.g., '|u1', '<f4')
    :param size: frame dimension in pixels and number of color components (height, width, components)
    :param squeeze: True to remove all the singular dimensions
    :return: dict holding the rawvideo frame data
    """

    sh = (len(b) // get_samplesize(shape, dtype), *shape)

    try:
        return {
            "buffer": b,
            "dtype": dtype,
            "shape": tuple(((i for i in sh if i != 1))) if squeeze else sh,
        }
    except:
        return None


@hookimpl
def bytes_to_audio(
    b: bytes, dtype: str, shape: Tuple[int], squeeze: bool
) -> BytesRawDataBlob:
    """convert bytes to rawaudio object

    :param b: byte data of arbitrary number of video frames
    :param dtype: numpy dtype string of the bytes (e.g., '<s2', '<f4')
    :param shape: number of interleaved audio channels (1-element tuple)
    :param squeeze: True to remove all the singular dimensions
    :return: dict to hold the raw audio samples
    """

    try:
        sh = (len(b) // get_samplesize(shape, dtype), *shape)

        return {
            "buffer": b,
            "dtype": dtype,
            "shape": tuple(((i for i in sh if i != 1))) if squeeze else sh,
        }
    except:
        return None
