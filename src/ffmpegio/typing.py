"""type hint definition for external use"""

from __future__ import annotations

from ._typing import (
    AudioFilterGraphInfoDict,
    CountDataCallable,
    DTypeString,
    EncodedInputInfoDict,
    EncodedOutputInfoDict,
    FFmpegInputType,
    FFmpegMediaType,
    FFmpegOptionDict,
    FFmpegOutputType,
    FFmpegUrlType,
    FileObjEncodedInputInfoDict,
    FileObjEncodedOutputInfoDict,
    FilterGraphInfoDict,
    FromBytesCallable,
    GetInfoCallable,
    InputInfoDict,
    InputPipeInfoDict,
    IsEmptyCallable,
    MediaType,
    OutputInfoDict,
    OutputPipeInfoDict,
    PipedEncodedInputInfoDict,
    PipeReader,
    PipeWriter,
    ProgressCallable,
    RawDataBlob,
    RawDirectOutputInfoDict,
    RawFilteredOutputInfoDict,
    RawInputInfoDict,
    RawOutputInfoDict,
    RawStreamDef,
    RawStreamInfoTuple,
    ShapeTuple,
    ToBytesCallable,
    UrlEncodedInputInfoDict,
    UrlOrPipedEncodedOutputInfoDict,
    VideoFilterGraphInfoDict,
)
from .plugins.rawdata_bytes import BytesRawDataBlob
from .configure import FFmpegArgs, FFmpegUrlType
from .filtergraph.abc import FilterGraphObject
from .stream_spec import StreamSpecDict, StreamSpecStreamType

__all__ = [
    "RawDataBlob",
    "BytesRawDataBlob",
    "DTypeString",
    "ShapeTuple",
    "FFmpegMediaType",
    "MediaType",
]
