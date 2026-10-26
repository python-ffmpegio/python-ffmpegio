"""ffmpegio object independent common type hints"""

from __future__ import annotations

from sys import version_info as _ver
from fractions import Fraction

try:
    from collections.abc import Buffer
except ImportError:
    Buffer = bytes | bytearray | memoryview

from typing import *


if TYPE_CHECKING:
    from namedpipe import NPopen

    from .threading import CopyFileObjThread

# typedef above
RawDataBlob: TypeAlias = Any
"""Python object representing media data frame.

    A :py:type:`RawDataBlob` must contain the shape and data format of the media data as well as the binary data.
    Any data frame format could be used if user provides a custom data I/O plugin for it. 
    The table below lists the natively supported data object types (each enabled by one of built-in plugins):

    =========================================================================================================== =========================================
    Raw Data Blob Object Type                                                                                   Plugin                                   
    =========================================================================================================== =========================================
    :py:class:`ffmpegio.typing.BytesRawDataBlob`                                                                :py:mod:`ffmpegio.plugins.rawdata_bytes`
    :py:type:`numpy.typing.ArrayLike`                                                                           :py:mod:`ffmpegio.plugins.rawdata_numpy`
    :py:class:`matplotlib.figure.Figure`                                                                        :py:mod:`ffmpegio.plugins.rawdata_mpl`
    :py:class:`PIL.Image.Image` | :py:class:`PIL.ImageSequence.Iterator` | :py:type:`Sequence[PIL.Image.Image]` :py:mod:`ffmpegio.plugins.rawdata_pillow`
    =========================================================================================================== =========================================
"""

DTypeString: TypeAlias = LiteralString
"""Numpy array interface protocol typestr string

    The string format consists of 3 parts: a character describing the byteorder of the data 
    (:code:`'<'`: little-endian, :code:`'>'`: big-endian, :code:`'|'`: not-relevant), a character code giving 
    the basic type of the array, and an integer providing the number of bytes the type uses.

    Three basic type character codes are relevant to :py:mod:`ffmpegio` package:

    =========== ================
    code        description
    =========== ================
    :code:`'i'` Integer
    :code:`'u'` Unsigned integer
    :code:`'f'` Floating point
    =========== ================
    
    See https://numpy.org/doc/stable/reference/arrays.interface.html for Numpy's
    official documentation.
"""

ShapeTuple: TypeAlias = tuple[int, ...]
"""Tuple whose elements are the array size in each dimension. Each entry is an integer (a Python int).

A video frame typically has 2 to 4 entries: :code:`([time, ]height, width[, color])`. 
An audio frame has either 1 or 2 entries: :code:`(time[, channel])`. 
"""

FFmpegMediaType = Literal["video", "audio", "subtitle", "data", "attachments"]
"""FFmpeg media stream types

    ===================== ==================
    value                 description
    ===================== ==================
    :code:`'video'`       video stream
    :code:`'audio'`       audio stream
    :code:`'subtitle'`    subtitle stream
    :code:`'data'`        data stream
    :code:`'attachments'` attachments stream
    ===================== ==================
"""

MediaType: TypeAlias = Literal["audio", "video"]
"""A subset of :py:type:`FFmpegMediaType` which is supported by :py:mod:`ffmpegio`

    =============== ============
    value           description
    =============== ============
    :code:`'video'` video stream
    :code:`'audio'` audio stream
    =============== ============
"""
FFmpegOptionDict: TypeAlias = dict[str, Any]
"""dict that hold FFmpeg option name-value pairs

FFmpeg options with their values keyed by the option names without preceding dash. 
For option flags (e.g., -y) without any value, use `None` or its alias `ffmpegio.FLAG`"""



RawStreamDef: TypeAlias = tuple[int | Fraction, RawDataBlob] | tuple[RawDataBlob, FFmpegOptionDict]
"""2-element tuple to define a raw stream data

    It comes in two forms: rate-data or data-option. The rate-data form specifies
    a pair of the frame rate (video) or sampling rate (audio) and the data blob.
    The data-option form specifies the data blob and its FFmpeg options. Note 
    that a data-option tuple is only valid if its option dict contains the rate
    field: `r` for video or `ar` for audio.

"""

RawStreamInfoTuple: TypeAlias = tuple[DTypeString, ShapeTuple, int | Fraction]
"""3-element tuple (dtype, shape, rate) to characterize raw data stream"""

ProgressCallable: TypeAlias = Callable[[dict[str, Any], bool], bool]
"""FFmpeg progress callback function

    callback(status, done)

      status - dict of encoding status
      done - True if the last callback

    The callback may return True to cancel the FFmpeg execution.
"""


FFmpegUrlType: TypeAlias = str
"""input and output file/stream urls (str or a stringifiable object)
"""

FFmpegInputType: TypeAlias = Literal["url", "filtergraph", "buffer", "fileobj"]
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

FFmpegOutputType: TypeAlias = Literal["url", "fileobj", "buffer"]
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

    def __call__(self, *, obj: object) -> memoryview: ...


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
    `'item_size`        size of each frame/sample in bytes
    `'data2bytes'`  conversion function
    `'data_is_empty'`   function to check empty data frame
    `'data_count'`      function to count number of frames/samples in a blob
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
    item_size: int
    """size of each frame/sample in bytes"""
    data2bytes: ToBytesCallable
    """converts a Python data blob to raw media bytes"""
    data_is_empty: IsEmptyCallable
    """returns True if the data blob is empty"""
    data_count: CountDataCallable
    """returns number of frames in the data blob"""
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


class PipeWriter(Protocol):
    def write(self, data: bytes | None): ...
    def join(self): ...
    def closed(self) -> bool: ...


class PipeReader(Protocol):
    def read(self, n: int = -1) -> bytes: ...
    def full(self) -> bool: ...
    def join(self): ...
    def cool_down(self): ...
    def clear(self): ...


class InputPipeInfoDict(TypedDict):
    """
    ==========  ==========================================
    `'pipe'`    named pipe assigned to this data stream
    `'writer'`  writer thread assigned to this data stream
    ==========  ==========================================
    """

    pipe: NPopen | Literal["stdin"]
    """named pipe assigned to this data stream"""
    writer: PipeWriter
    """writer thread assigned to this data stream"""


##################################################


class RawDirectOutputInfoDict(TypedDict):
    """raw output media stream info

    =================== ================================================================
    key                 description
    =================== ================================================================
    `'dst_type'`        `'buffer'`
    `'media_type'`      media stream identifier: `'audio'` or '`video'`
    `'raw_info'`        tuple of (dtype, shape, rate)
    `'item_size`        size of each frame/sample in bytes
    `'bytes2data'`      function to convert bytes to raw data blob
    `'data_is_empty'`   function to check empty data frame
    `'data_count'`      function to count number of frames/samples in a blob
    `'user_map'`        user specified FFmpeg map option of this stream
    `'squeeze'`         True to squeeze output shape (remove all length-1 dims)
    `'input_file_id'`   input file id
    `'input_stream_id'` input stream id
    =================== ================================================================
    """

    dst_type: Literal["buffer"]  # True if file path/url
    media_type: MediaType  #
    raw_info: RawStreamInfoTuple
    bytes2data: FromBytesCallable
    item_size: int
    data_is_empty: IsEmptyCallable
    data_count: CountDataCallable
    user_map: str  # user specified map option
    squeeze: bool
    input_file_id: NotRequired[int]
    input_stream_id: NotRequired[int]


class RawFilteredOutputInfoDict(TypedDict):
    """raw output media stream info

    =================== ================================================================
    key                 description
    =================== ================================================================
    `'dst_type'`        `'buffer'`
    `'media_type'`      media stream identifier: `'audio'` or '`video'`
    `'raw_info'`        tuple of (dtype, shape, rate)
    `'item_size`        size of each frame/sample in bytes
    `'bytes2data'`      function to convert bytes to raw data blob
    `'data_is_empty'`   function to check empty data frame
    `'data_count'`      function to count number of frames/samples in a blob
    `'user_map'`        user specified FFmpeg map option of this stream
    `'squeeze'`         True to squeeze output shape (remove all length-1 dims)
    `'linklabel'`       mapped filtergraph output label
    =============== ================================================================
    """

    dst_type: Literal["buffer"]  # True if file path/url
    media_type: MediaType  #
    raw_info: RawStreamInfoTuple
    item_size: int
    bytes2data: FromBytesCallable
    data_is_empty: IsEmptyCallable
    data_count: CountDataCallable
    user_map: str  # user specified map option
    squeeze: bool
    linklabel: str


RawOutputInfoDict = RawDirectOutputInfoDict | RawFilteredOutputInfoDict
"""raw output media stream info

=================== ================================================================
key                 description
=================== ================================================================
`'dst_type'`        `'buffer'`
`'media_type'`      media stream identifier: `'audio'` or '`video'`
`'raw_info'`        tuple of (dtype, shape, rate)
`'bytes2data'`      function to convert bytes to raw data blob
`'data_is_empty'`   function to check empty raw data blob
`'data_count'`      function to count number of frames/samples in a blob
`'squeeze'`         True to squeeze output shape (remove all length-1 dims)
`'input_file_id'`   (optional) input file id if there is no complex filtergraph
`'input_stream_id'` (optional) input stream id if there is no complex filtergraph
`'linklabel'`       (optional) mapped filtergraph output label if there is complex
                    filtergraph
=============== ================================================================
"""


class UrlOrPipedEncodedOutputInfoDict(TypedDict):
    """url/filtergraph encoded input source info"""

    dst_type: Literal["url", "buffer"]
    """output data goes to either a url/filepath or a pipe"""


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

    pipe: NPopen | Literal["stdout"]
    reader: PipeReader | CopyFileObjThread
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
