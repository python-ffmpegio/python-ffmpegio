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


FFmpegOptionDict = dict[str, Any]
"""FFmpeg options with their values keyed by the option names without preceding dash. 
For option flags (e.g., -y) without any value, use `None` or its alias `ffmpegio.FLAG`"""

RawDataBlob = Any
"""any object to represent raw binary data supported by a data I/O plugin."""

DTypeString = LiteralString
"""Numpy array interface protocol typestr string

The string format consists of 3 parts: a character describing the byteorder of the data 
(`'<'`: little-endian, `'>'`: big-endian, `'|'`: not-relevant), a character code giving 
the basic type of the array, and an integer providing the number of bytes the type uses.

Three basic type character codes are relevant to `ffmpegio` package:

===== ================
code  description
===== ================
`'i'` Integer
`'u'` Unsigned integer
`'f'` Floating point
===== ================

See https://numpy.org/doc/stable/reference/arrays.interface.html for Numpy's
official documentation.
"""

ShapeTuple = tuple[int, ...]
"""Tuple whose elements are the array size in each dimension. Each entry is an integer (a Python int)."""


RawStreamDef = (
    tuple[int | Fraction, RawDataBlob] | tuple[RawDataBlob | None, FFmpegOptionDict]
)
"""2-element tuple to define a raw stream data

    It comes in two forms: rate-data or data-option. The rate-data form specifies
    a pair of the frame rate (video) or sampling rate (audio) and the data blob.
    The data-option form specifies the data blob and its FFmpeg options. Note 
    that a data-option tuple is only valid if its option dict contains the rate
    field: `r` for video or `ar` for audio.

"""

RawStreamInfoTuple = tuple[DTypeString, ShapeTuple, int | Fraction]
"""3-element tuple (rate, shape, dtype) to characterize raw data stream"""

ProgressCallable = Callable[[dict[str, Any], bool], bool]
"""FFmpeg progress callback function

    callback(status, done)

      status - dict of encoding status
      done - True if the last callback

    The callback may return True to cancel the FFmpeg execution.
"""

MediaType = Literal["audio", "video"]

FFmpegMediaType = Literal["video", "audio", "subtitle", "data", "attachments"]

FFmpegUrlType = str | Path | ParseResult

FFmpegInputType = Literal["url", "filtergraph", "buffer", "fileobj"]
FFmpegOutputType = Literal["url", "fileobj", "buffer"]


class InputSourceDict(TypedDict):
    """input source info"""

    src_type: FFmpegInputType  # True if file path/url
    buffer: NotRequired[bytes]  # index of the source index
    fileobj: NotRequired[IO]  # file object
    media_type: NotRequired[MediaType]  # media type if input pipe
    raw_info: NotRequired[RawStreamInfoTuple]
    writer: NotRequired[WriterThread]  # pipe


class OutputDestinationDict(TypedDict):
    """output source info"""

    dst_type: FFmpegOutputType  # True if file path/url
    user_map: str | None  # user specified map option
    media_type: MediaType | None  #
    input_file_id: NotRequired[int]
    input_stream_id: NotRequired[int]
    linklabel: NotRequired[str]
    raw_info: NotRequired[RawStreamInfoTuple]
    pipe: NotRequired[NPopen]
    reader: NotRequired[ReaderThread]
    itemsize: NotRequired[int]
    nmin: NotRequired[int]
