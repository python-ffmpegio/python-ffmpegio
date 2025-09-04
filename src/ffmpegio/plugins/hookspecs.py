from __future__ import annotations

import pluggy
from typing import Protocol, Callable
from .._typing import DTypeString, ShapeTuple

hookspec = pluggy.HookspecMarker("ffmpegio")


@hookspec(firstresult=True)
def finder() -> tuple[str, str]:
    """find ffmpeg and ffprobe executable"""
    ...

class GetInfoCallable(Protocol):
    def __call__(self, *, obj: object) -> tuple[ShapeTuple, DTypeString]: ...


@hookspec(firstresult=True)
def video_info(obj: object) -> tuple[ShapeTuple, DTypeString]:
    """get video frame info

    :param obj: object containing video frame data with arbitrary number of frames
    :return shape: shape (height,width,components)
    :return dtype: data type in numpy dtype str expression
    """
    ...


@hookspec(firstresult=True)
def audio_info(obj: object) -> tuple[ShapeTuple, DTypeString]:
    """get audio sample info

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :return ac: number of channels
    :return dtype: sample data type in numpy dtype str expression
    """
    ...


class ToBytesCallable(Protocol):
    def __call__(self, *, obj: object) -> memoryview: ...


@hookspec(firstresult=True)
def video_bytes(obj: object) -> memoryview:
    """return bytes-like object of packed video pixels, associated with `video_info()`

    :param obj: object containing video frame data with arbitrary number of frames
    :return: packed bytes of video frames
    """
    ...


@hookspec(firstresult=True)
def audio_bytes(obj: object) -> memoryview:
    """return bytes-like object of packed audio samples

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :return: packed bytes of audio samples
    """
    ...


class CountDataCallable(Protocol):
    def __call__(
        self, *, b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
    ) -> int: ...


@hookspec(firstresult=True)
def video_frames(obj: object) -> int:
    """get number of video frames in obj

    :param obj: object containing video frame data with arbitrary number of frames
    :return: number of video frames in obj
    """
    ...


@hookspec(firstresult=True)
def audio_samples(obj: object) -> int:
    """get audio sample info

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :return: number of samples in obj
    """
    ...


class FromBytesCallable(Protocol):
    def __call__(
        self, *, b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
    ) -> object: ...


@hookspec(firstresult=True)
def bytes_to_video(
    b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
) -> object:
    """convert bytes to rawvideo object

    :param b: byte data of arbitrary number of video frames
    :param dtype: data type numpy dtype string (e.g., '|u1', '<f4')
    :param size: frame dimension in pixels and number of color components (height, width, components)
    :param squeeze: True to remove all the singular dimensions
    :return: python object holding the rawvideo frames
    """


@hookspec(firstresult=True)
def bytes_to_audio(
    b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
) -> object:
    """convert bytes to rawaudio object

    :param b: byte data of arbitrary number of video frames
    :param dtype: numpy dtype string of the bytes (e.g., '<s2', '<f4')
    :param shape: number of interleaved audio channels (1-element tuple)
    :param squeeze: True to remove all the singular dimensions
    :return: python object to hold the raw audio samples
    """


@hookspec
def device_source_api() -> tuple[str, dict[str, Callable]]:
    """return a source name and its set of interface functions

    keyword/signature                      Descriptions
    -------------------------------------  -------------------------------------------------------
    scan() -> dict[str, dict]              scan system for available hardware
    resolve(infos: set[dict]) -> str       resolve stream specifier type url to proper device url
    list_options(name: str) -> List[dict]  list available device options (some may return a range)

    Partial definition is OK
    """
    ...


@hookspec
def device_sink_api() -> tuple[str, dict[str, Callable]]:
    """return a sink name and its set of interface functions

    keyword/signature                       Descriptions
    --------------------------------------  -------------------------------------------------------
    scan() -> dict[str, dict]               scan system for available hardware
    resolve(infos: set[dict]) -> str        resolve stream specifier type url to proper device url
    list_options(info: dict) -> List[dict]  list available device options (some may return a range)

    Partial definition is OK
    """
    ...

class HasDataCallable(Protocol):
    def __call__(self, *, obj: object) -> bool: ...


@hookspec(firstresult=True)
def is_empty(obj: object) -> bool:
    """True if data blob object has no data

    :param obj: object containing media data
    """
    ...
