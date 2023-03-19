from .._utils import get_samplesize
from pluggy import HookimplMarker
from typing import Tuple

hookimpl = HookimplMarker("ffmpegio")


@hookimpl
def video_info(obj: dict) -> Tuple[Tuple[int, int, int], str]:
    """get video frame info

    :param obj: dict containing video frame data with arbitrary number of frames
    :type obj: object
    :return: shape (height,width,components) and data type in numpy dtype str expression
    :rtype: Tuple[Tuple[int, int, int], str]
    """

    try:
        return obj["shape"][-3:], obj["dtype"]
    except:
        return None


@hookimpl
def audio_info(obj: object) -> Tuple[int, str]:
    """get audio sample info

    :param obj: dict containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: dict
    :return: number of channels and sample data type in numpy dtype str expression
    :rtype: Tuple[Tuple[int], str]
    """
    try:
        return obj["shape"][-1:], obj["dtype"]
    except:
        return None


@hookimpl
def video_bytes(obj: object) -> memoryview:
    """return bytes-like object of packed video pixels, associated with `video_info()`

    :param obj: dict containing video frame data with arbitrary number of frames
    :type obj: dict
    :return: packed bytes of video frames
    :rtype: bytes-like object
    """

    try:
        return obj["buffer"]
    except:
        return None


@hookimpl
def audio_bytes(obj: object) -> memoryview:
    """return bytes-like object of packed audio samples

    :param obj: dict containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: dict
    :return: packed bytes of audio samples
    :rtype: bytes-like object
    """

    try:
        return obj["buffer"]
    except:
        return None


@hookimpl
def bytes_to_video(
    b: bytes, dtype: str, shape: Tuple[int, int, int], squeeze: bool
) -> object:
    """convert bytes to rawvideo object

    :param b: byte data of arbitrary number of video frames
    :type b: bytes
    :param dtype: data type numpy dtype string (e.g., '|u1', '<f4')
    :type dtype: str
    :param size: frame dimension in pixels and number of color components (height, width, components)
    :type size: Tuple[int, int, int]
    :param squeeze: True to remove all the singular dimensions
    :type squeeze: bool
    :return: dict holding the rawvideo frame data
    :rtype: dict['buffer':bytes, 'dtype':str, 'shape': Tuple[int,int,int]]
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
def bytes_to_audio(b: bytes, dtype: str, shape: Tuple[int], squeeze: bool) -> object:
    """convert bytes to rawaudio object

    :param b: byte data of arbitrary number of video frames
    :type b: bytes
    :param dtype: numpy dtype string of the bytes (e.g., '<s2', '<f4')
    :type dtype: str
    :param shape: number of interleaved audio channels (1-element tuple)
    :type shape: Tuple[int]
    :param squeeze: True to remove all the singular dimensions
    :type squeeze: bool
    :return: dict to hold the raw audio samples
    :rtype: dict['buffer':bytes, 'dtype':str, 'shape': Tuple[int]]
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
