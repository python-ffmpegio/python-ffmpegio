from __future__ import annotations

import pluggy
from typing import Callable, Tuple

hookspec = pluggy.HookspecMarker("ffmpegio")


@hookspec(firstresult=True)
def finder() -> Tuple[str, str]:
    """find ffmpeg and ffprobe executable"""


@hookspec(firstresult=True)
def video_info(obj: object) -> Tuple[Tuple[int, int, int], str]:
    """get video frame info

    :param obj: object containing video frame data with arbitrary number of frames
    :type obj: object
    :return: shape (height,width,components) and data type in numpy dtype str expression
    :rtype: Tuple[Tuple[int, int, int], str]
    """


@hookspec(firstresult=True)
def audio_info(obj: object) -> Tuple[int, str]:
    """get audio sample info

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: object
    :return: number of channels and sample data type in numpy dtype str expression
    :rtype: Tuple[Tuple[int], str]
    """


@hookspec(firstresult=True)
def video_bytes(obj: object) -> memoryview:
    """return bytes-like object of packed video pixels, associated with `video_info()`

    :param obj: object containing video frame data with arbitrary number of frames
    :type obj: object
    :return: packed bytes of video frames
    :rtype: bytes-like object
    """


@hookspec(firstresult=True)
def audio_bytes(obj: object) -> memoryview:
    """return bytes-like object of packed audio samples

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: object
    :return: packed bytes of audio samples
    :rtype: bytes-like object
    """


@hookspec(firstresult=True)
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
    :return: python object holding the rawvideo frames
    :rtype: object
    """


@hookspec(firstresult=True)
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
    :return: python object to hold the raw audio samples
    :rtype: object
    """


@hookspec
def device_source_api() -> Tuple[str, dict[str, Callable]]:
    """return a source name and its set of interface functions

    keyword/signature                      Descriptions
    -------------------------------------  -------------------------------------------------------
    scan() -> dict[str, dict]              scan system for available hardware
    resolve(infos: set[dict]) -> str       resolve stream specifier type url to proper device url
    list_options(name: str) -> List[dict]  list available device options (some may return a range)

    Partial definition is OK
    """


@hookspec
def device_sink_api() -> Tuple[str, dict[str, Callable]]:
    """return a sink name and its set of interface functions

    keyword/signature                       Descriptions
    --------------------------------------  -------------------------------------------------------
    scan() -> dict[str, dict]               scan system for available hardware
    resolve(infos: set[dict]) -> str        resolve stream specifier type url to proper device url
    list_options(info: dict) -> List[dict]  list available device options (some may return a range)

    Partial definition is OK
    """
