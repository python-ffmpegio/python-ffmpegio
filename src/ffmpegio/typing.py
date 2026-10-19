"""type hint definition for external use"""

from __future__ import annotations

from ._typing import (
    FFmpegOptionDict,
    RawDataBlob,
    DTypeString,
    ShapeTuple,
    RawStreamDef,
    RawStreamInfoTuple,
    ProgressCallable,
    MediaType,
    FFmpegMediaType,
    FFmpegUrlType,
    FFmpegInputType,
    FFmpegOutputType,
    GetInfoCallable,
    ToBytesCallable,
    CountDataCallable,
    FromBytesCallable,
    IsEmptyCallable,
    RawInputInfoDict,
    UrlEncodedInputInfoDict,
    PipedEncodedInputInfoDict,
    FileObjEncodedInputInfoDict,
    EncodedInputInfoDict,
    InputInfoDict,
    PipeWriter,
    PipeReader,
    InputPipeInfoDict,
    RawDirectOutputInfoDict,
    RawFilteredOutputInfoDict,
    RawOutputInfoDict,
    UrlOrPipedEncodedOutputInfoDict,
    FileObjEncodedOutputInfoDict,
    EncodedOutputInfoDict,
    OutputInfoDict,
    OutputPipeInfoDict,
    AudioFilterGraphInfoDict,
    VideoFilterGraphInfoDict,
    FilterGraphInfoDict,
)
from .configure import FFmpegArgs, FFmpegUrlType
from .filtergraph.abc import FilterGraphObject
from .stream_spec import StreamSpecDict, StreamSpecStreamType
