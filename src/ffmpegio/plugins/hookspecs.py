from __future__ import annotations

import pluggy

from .._typing import Callable, DTypeString, RawDataBlob, ShapeTuple

hookspec = pluggy.HookspecMarker("ffmpegio")


@hookspec(firstresult=True)
def finder() -> tuple[str, str] | None:
    """find ffmpeg and ffprobe executables

    :return: a tuple containing

        - (str) ffmpeg executable path
        - (str) ffprobe executable path

        or None if the plugin could not resolve these paths
    :rtype: tuple | None

    """


@hookspec(firstresult=True)
def video_info(obj: RawDataBlob) -> tuple[ShapeTuple, DTypeString] | None:
    """get video frame info

    :param obj: object containing video frame data with arbitrary number of frames
    :type obj: RawDataBlob
    :return: a tuple containing

        - (:py:type:`ShapeTuple <ffmpegio.typing.ShapeTuple>`) shape of a video frame (height,width,components)
        - (:py:type:`DTypeString <ffmpegio.typing.DTypeString>`) data type in numpy dtype str expression

        or None if plugin does not support the given obj data
    :rtype: tuple | None
    """


@hookspec(firstresult=True)
def audio_info(obj: RawDataBlob) -> tuple[ShapeTuple, DTypeString] | None:
    """get audio sample info

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: RawDataBlob
    :return: a tuple containing

        - (int) number of channels in obj
        - (:py:type:`DTypeString <ffmpegio.typing.DTypeString>`) data type in numpy dtype str expression

        or None if plugin does not support the given obj data
    :rtype: tuple | None
    """


@hookspec(firstresult=True)
def video_bytes(obj: RawDataBlob) -> memoryview:
    """return bytes-like object of packed video pixels, associated with :py:func:`video_info() <ffmpegio.plugins.hookspecs.video_info()>`

    :param obj: object containing video frame data with arbitrary number of frames
    :type obj: RawDataBlob
    :return: packed bytes of video frames
    """


@hookspec(firstresult=True)
def audio_bytes(obj: RawDataBlob) -> memoryview:
    """return bytes-like object of packed audio samples

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: RawDataBlob
    :return: packed bytes of audio samples
    """


@hookspec(firstresult=True)
def video_frames(obj: RawDataBlob) -> int:
    """get number of video frames in obj

    :param obj: object containing video frame data with arbitrary number of frames
    :type obj: RawDataBlob
    :return: number of video frames in obj
    """


@hookspec(firstresult=True)
def audio_samples(obj: RawDataBlob) -> int:
    """get audio sample info

    :param obj: object containing audio data (with interleaving channels) with arbitrary number of samples
    :type obj: RawDataBlob
    :return: number of samples in obj
    """


@hookspec(firstresult=True)
def bytes_to_video(
    b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
) -> RawDataBlob:
    """convert bytes to rawvideo object

    :param b: byte data of arbitrary number of video frames
    :param dtype: data type numpy dtype string (e.g., :code:`'|u1'`, :code:`'<f4'`)
    :type dtype: DTypeString
    :param shape: frame dimension in pixels and number of color components (height, width, components)
    :type shape: ShapeTuple
    :param squeeze: True to remove all the singular dimensions
    :return: python object holding the rawvideo frames
    :rtype: RawDataBlob

    """


@hookspec(firstresult=True)
def bytes_to_audio(
    b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
) -> RawDataBlob:
    """convert bytes to rawaudio object

    :param b: byte data of arbitrary number of video frames
    :param dtype: numpy dtype string of the bytes (e.g., '<s2', '<f4')
    :type dtype: DTypeString
    :param shape: number of interleaved audio channels (1-element tuple)
    :type shape: ShapeTuple
    :param squeeze: True to remove all the singular dimensions
    :return: python object to hold the raw audio samples
    :rtype: RawDataBlob

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


@hookspec(firstresult=True)
def is_empty(obj: object) -> bool:
    """True if data blob object has no data

    :param obj: object containing media data
    """
