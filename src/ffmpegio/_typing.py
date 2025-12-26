"""ffmpegio object independent common type hints"""

from __future__ import annotations

from typing_extensions import *

from fractions import Fraction
from pathlib import Path
from urllib.parse import ParseResult as UrlParseResult


if TYPE_CHECKING:
    from namedpipe import NPopen
    from .threading import WriterThread, ReaderThread, CopyFileObjThread

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
"""3-element tuple (dtype, shape, rate) to characterize raw data stream"""

ProgressCallable = Callable[[dict[str, Any], bool], bool]
"""FFmpeg progress callback function

    callback(status, done)

      status - dict of encoding status
      done - True if the last callback

    The callback may return True to cancel the FFmpeg execution.
"""

MediaType = Literal["audio", "video"]
"""supported media stream types

=============== ================================================================
value           description
=============== ================================================================
`'video'`       video stream
`'audio'`       audio stream
=============== ================================================================
"""

FFmpegMediaType = Literal["video", "audio", "subtitle", "data", "attachments"]
"""FFmpeg media stream types

=============== ================================================================
value           description
=============== ================================================================
`'video'`       video stream
`'audio'`       audio stream
`'subtitle'`    subtitle stream
`'data'`        data stream
`'attachments'` attachments stream
=============== ================================================================
"""

FFmpegUrlType = str | Path | UrlParseResult
"""input and output file/stream urls 
"""

FFmpegInputType = Literal["url", "filtergraph", "buffer", "fileobj"]
"""mechanisms to feed encoded input data to FFmpeg input pipe

=============== ================================================================
value           description
=============== ================================================================
`'url'`         path to the input file or streaming url
`'filtergraph'` input filtergraph
`'buffer'`      binary input data given as a bytes-like object or to be piped in
`'fileobj'`     open readable file object
=============== ================================================================
"""

FFmpegOutputType = Literal["url", "fileobj", "buffer"]
"""mechanisms to extract encoded output data from FFmpeg output pipe

=============== ============================================================================
value           description
=============== ============================================================================
`'url'`         path to the output file or streaming url
`'buffer'`      buffer output data as `RawDataBlob` (raw stream) or `bytes` (encoded stream)
`'fileobj'`     open readable file object
=============== ============================================================================
"""

##################
# Plugin protocols
##################


class GetInfoCallable(Protocol):
    """Plugin function prototype to get information of a raw data blob object

    A plugin may implement this prototype with `audio_info()` for audio stream or
    `video_info()` for video/image stream.

    :param obj: Plugin-specific raw data blob object
    :return shape: tuple of `int`s of the raw data shape
    :return dtype: numpy dtype string of a video/image pixel or an audio sample
    """

    def __call__(self, *, obj: object) -> tuple[ShapeTuple, DTypeString]: ...


class ToBytesCallable(Protocol):
    """Plugin function prototype to convert raw data blob object to a byte buffer

    A plugin may implement this prototype with `audio_bytes()` for audio stream or
    `video_bytes()` for video/image stream.

    :param obj: Plugin-specific raw data blob object
    :return: a FFmpeg raw media stream compatible bytes
    """

    def __call__(self, obj: object) -> memoryview: ...


class CountDataCallable(Protocol):
    """Plugin function prototype to count a number of video frames/audio samples

    A plugin may implement this prototype with `audio_samples()` for audio stream or
    `video_frames()` for video/image stream.

    :param obj: Plugin-specific raw data blob object
    :return: number of video frames or of audio samples
    """

    def __call__(self, *, obj: object) -> int: ...


class FromBytesCallable(Protocol):
    """Plugin function prototype to convert FFmpeg output bytes to raw data blob

    A plugin may implement this prototype with `bytes_to_audio()` for audio stream or
    `bytes_to_video()` for video stream.

    :param b: FFmpeg output of raw audio/video/image frames
    :param dtype: numpy dtype string of pixel/sample data format
    :param shape: tuple of the dimension of one video frame or one audio sample.
                  Audio: (channels,), Video: (height, width, components)
    :param squeeze: True to remove all dimensions with length 1
    :return: Plugin-specific raw data blob object
    """

    def __call__(
        self, b: bytes, dtype: DTypeString, shape: ShapeTuple, squeeze: bool
    ) -> object: ...


class IsEmptyCallable(Protocol):
    """Plugin function prototype to check if data blob contains no data

    A plugin may implement this prototype with `audio_samples()` for audio stream or
    `video_frames()` for video/image stream.

    :param obj: Plugin-specific raw data blob object
    :return: True if the blob contains no data
    """

    def __call__(self, *, obj: object) -> bool: ...


######


class RawInputInfoDict(TypedDict):
    """raw input media stream information

    =============== ================================================================
    key             description
    =============== ================================================================
    `'src_type'`    always `'buffer'`
    `'media_type'`  media stream identifier: `'audio'` or '`video'`
    `'raw_info'`    tuple of (rate, shape, dtype)
    `'data2bytes'`  conversion function
    `'buffer'`      (optional) known media data blobs to be input (typically for
                    a batch operation)
    `'pipe'`        (optional) named pipe assigned to this data stream
    `'writer'`      (optional) writer thread assigned to this data stream
    =============== ================================================================
    """

    src_type: Literal["buffer"]
    """True if file path/url"""
    media_type: MediaType
    """media type if input pipe"""
    raw_info: RawStreamInfoTuple
    """tuple of (rate, shape, dtype)"""
    data2bytes: ToBytesCallable
    """converts a Python data blob to raw media bytes"""
    buffer: NotRequired[object]
    """stores data blob (typically for batch operation)"""


class UrlEncodedInputInfoDict(TypedDict):
    """url/filtergraph encoded input source info"""

    src_type: Literal["url", "filtergraph"]
    """input data is from a url/file or from an input filtergraph"""


class PipedEncodedInputInfoDict(TypedDict):
    """piped encoded input source info"""

    src_type: Literal["buffer"]
    buffer: NotRequired[bytes]  # index of the source index


class FileObjEncodedInputInfoDict(TypedDict):
    """fileobj encoded input info"""

    src_type: Literal["fileobj"]
    fileobj: IO  # file object


EncodedInputInfoDict = (
    UrlEncodedInputInfoDict | PipedEncodedInputInfoDict | FileObjEncodedInputInfoDict
)
"""encoded input container stream information

=============== ================================================================
key             description
=============== ================================================================
`'src_type'`    `'url'`, `'filtergraph'`, `'buffer'`, or `'fileobj'`
`'buffer'`      (optional for `src_type = 'buffer') known media data bytes to be 
                input (typically for a batch operation)
=============== ================================================================
"""

InputInfoDict = RawInputInfoDict | EncodedInputInfoDict


class InputPipeInfoDict(TypedDict):
    """
    ==========  ==========================================
    `'pipe'`    named pipe assigned to this data stream
    `'writer'`  writer thread assigned to this data stream
    ==========  ==========================================
    """

    pipe: NPopen
    """named pipe assigned to this data stream"""
    writer: WriterThread
    """writer thread assigned to this data stream"""


##################################################


class RawOutputInfoDict(TypedDict):
    """raw output media stream info

    =================== ================================================================
    key                 description
    =================== ================================================================
    `'dst_type'`        `'buffer'`
    `'media_type'`      media stream identifier: `'audio'` or '`video'`
    `'raw_info'`        tuple of (dtype, shape, rate)
    `'data_info'`       function to gather media information from raw data blob
    `'bytes2data'`      function to convert bytes to raw data blob
    `'is_empty'`        function to check empty data frame check
    `'user_map'`        (optional) user specified FFmpeg map option of this stream
    `'input_file_id'`   (optional) input file id if there is no complex filtergraph
    `'input_stream_id'` (optional) input stream id if there is no complex filtergraph
    `'linklabel'`       (optional) mapped filtergraph output label if there is complex
                        filtergraph
    =============== ================================================================
    """

    dst_type: Literal["buffer"]  # True if file path/url
    media_type: MediaType | None  #
    data_info: GetInfoCallable
    bytes2data: FromBytesCallable
    is_empty: IsEmptyCallable
    user_map: NotRequired[str]  # user specified map option
    input_file_id: NotRequired[int]
    input_stream_id: NotRequired[int]
    linklabel: NotRequired[str]
    raw_info: NotRequired[RawStreamInfoTuple]


class UrlOrPipedEncodedOutputInfoDict(TypedDict):
    """url/filtergraph encoded input source info"""

    dst_type: Literal["url", "buffer"]
    """output data goes to either a url/file or a pipe"""


class FileObjEncodedOutputInfoDict(TypedDict):
    """fileobj encoded input info"""

    dst_type: Literal["fileobj"]
    fileobj: IO  # file object


EncodedOutputInfoDict = UrlOrPipedEncodedOutputInfoDict | FileObjEncodedOutputInfoDict
"""encoded output container stream information

=============== ================================================================
key             description
=============== ================================================================
`'src_type'`    `'url'`, `'filtergraph'`, `'buffer'`, or `'fileobj'`
`'buffer'`      (optional for `src_type = 'buffer') known media data bytes to be
                input (typically for a batch operation)
`'pipe'`        (optional for `src_type` is `'buffer'` or `'fileobj'`)
                named pipe assigned to this data stream
`'writer'`      (optional for `src_type` is `'buffer'` or `'fileobj'`)
                writer thread assigned to this data stream
=============== ================================================================
"""


OutputInfoDict = RawOutputInfoDict | EncodedOutputInfoDict
"""combined output info"""


class OutputPipeInfoDict(TypedDict):
    """
    =============== ================================================================
    `'pipe'`            named pipe assigned to this data stream
    `'reader'`          reader thread assigned to this data stream
    `'itemsize'`        (optional) one frame/sample size in bytes
    `'nmin'`            (optional) minimum read block size
    =============== ================================================================
    """

    pipe: NPopen
    reader: ReaderThread | CopyFileObjThread
    itemsize: NotRequired[int]
    nmin: NotRequired[int]


##################################################


class AudioFilterGraphInfoDict(TypedDict):
    media_type: Literal["audio"]
    sample_fmt: str
    ac: int
    ar: int


class VideoFilterGraphInfoDict(TypedDict):
    media_type: Literal["video"]
    r: int | Fraction
    pix_fmt: str


FilterGraphInfoDict = AudioFilterGraphInfoDict | VideoFilterGraphInfoDict
