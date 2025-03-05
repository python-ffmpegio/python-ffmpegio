"""ffmpegio object independent common type hints"""

from __future__ import annotations

from typing import *
from typing_extensions import *

from fractions import Fraction
from pathlib import Path
from urllib.parse import ParseResult


if TYPE_CHECKING:
    from namedpipe import NPopen
    from .threading import WriterThread, ReaderThread

# from typing_extensions import *


RawDataBlob = Any  # depends on raw data reader plugin

RawStreamDef = (
    tuple[int | float | Fraction, RawDataBlob]
    | tuple[RawDataBlob | None, dict[str, Any]]
)


ProgressCallable = Callable[[dict[str, Any], bool], bool]
"""FFmpeg progress callback function

    callback(status, done)

      status - dict of encoding status
      done - True if the last callback

    The callback may return True to cancel the FFmpeg execution.
"""

MediaType = Literal["audio", "video"]

FFmpegMediaType = Literal["video", "audio", "subtitle", "data", "attachments"]

FFmpegUrlType = Union[str, Path, ParseResult]

FFmpegInputType = Literal["url", "filtergraph", "buffer", "fileobj"]
FFmpegOutputType = Literal["url", "fileobj", "buffer"]


class InputSourceDict(TypedDict):
    """input source info"""

    src_type: FFmpegInputType  # True if file path/url
    buffer: NotRequired[bytes]  # index of the source index
    fileobj: NotRequired[IO]  # file object
    media_type: NotRequired[MediaType]  # media type if input pipe
    writer: NotRequired[WriterThread]  # pipe


class OutputDestinationDict(TypedDict):
    """output source info"""

    dst_type: FFmpegOutputType  # True if file path/url
    user_map: str | None  # user specified map option
    media_type: MediaType | None  #
    input_file_id: NotRequired[int]
    input_stream_id: NotRequired[int]
    linklabel: NotRequired[str]
    media_info: NotRequired[dict[str, Any]]
    pipe: NotRequired[NPopen]
    reader: NotRequired[ReaderThread]
    itemsize: NotRequired[int]
    nmin: NotRequired[int]
