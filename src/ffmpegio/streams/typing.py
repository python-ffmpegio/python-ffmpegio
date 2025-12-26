from __future__ import annotations

from fractions import Fraction
from .._typing import (
    MediaType,
    DTypeString,
    ShapeTuple,
    Any,
    Protocol,
    RawInputInfoDict,
    RawOutputInfoDict,
    EncodedInputInfoDict,
    EncodedOutputInfoDict,
)


class FrameReaderProtocol(Protocol):

    def output_label(self, stream_index: int = 0) -> str | None:
        """FFmpeg/custom label of the output stream in FFmpeg"""

    def output_type(self, stream_index: int = 0) -> MediaType | None:
        """media type associated with the output stream (key)"""

    def output_rate(self, stream_index: int = 0) -> int | Fraction | None:
        """sample or frame rates associated with the output stream (key)"""

    def output_dtype(self, stream_index: int = 0) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""

    def output_shape(self, stream_index: int = 0) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""

    def output_count(self, stream_index: int = 0) -> int:
        """number of frames/samples read"""

    def output_bytesize(self, stream_index: int = 0) -> int | None:
        """number of bytes per output sample/pixel"""

    @property
    def output_labels(self) -> list[str | None]:
        """FFmpeg/custom labels of output streams if specified"""
        ...

    @property
    def output_types(self) -> list[MediaType | None]:
        """media type associated with the output streams (key)"""
        ...

    @property
    def output_rates(self) -> list[int | Fraction | None]:
        """sample or frame rates associated with the output streams (key)"""
        ...

    @property
    def output_dtypes(self) -> list[DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""
        ...

    @property
    def output_shapes(self) -> list[ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""
        ...

    @property
    def output_counts(self) -> list[int]:
        """number of frames/samples read"""
        ...

    @property
    def output_bytesizes(self) -> list[int | None]:
        """number of bytes per output sample/pixel"""
        ...

    def read(self, n: int = -1, timeout: float | None = None) -> Any:
        """read n raw frames from FFmpeg

        :param n: number of samples/frames to read, if negative, read all frames,
                  defaults to -1
        :param timeout: timeout in seconds, defaults to None
        :return: n frames of data data type depending on the active plugin. A frame
                 is one video image or a set of audio samples at one sample time.
        """


class FrameWriterProtocol(Protocol):
    """to write raw frame data to FFmpeg"""

    def input_type(self, stream_id: int = 0) -> MediaType | None:
        """media type associated with the input streams"""

    def input_rate(self, stream_id: int = 0) -> int | Fraction | None:
        """sample or frame rates associated with the input streams"""

    def input_dtype(self, stream_id: int = 0) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""

    def input_shape(self, stream_id: int = 0) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""

    def input_count(self, stream_id: int = 0) -> int:
        """number of input frames/samples written"""

    def input_bytesize(self, stream_id: int = 0) -> int | None:
        """input sample/pixel count per frame"""

    @property
    def input_types(self) -> list[MediaType]:
        """media type associated with the input streams"""

    @property
    def input_rates(self) -> list[int | Fraction]:
        """sample or frame rates associated with the input streams"""

    @property
    def input_dtypes(self) -> list[DTypeString]:
        """frame/sample data type associated with the output streams (key)"""

    @property
    def input_shapes(self) -> list[ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""

    @property
    def input_counts(self) -> list[int]:
        """number of input frames/samples written"""

    @property
    def input_bytesizes(self) -> list[int | None]:
        """input sample/pixel count per frame"""

    def write(self, data: Any, timeout: float | None = None):
        """write raw frame data

        :param data: _description_
        :param timeout: _description_, defaults to None
        """

    def flush(self, timeout: float | None = None):
        """block until the write buffer is emptied

        :param timeout: a timeout for blocking in seconds, or fractions
                        thereof, defaults to None, to wait until empty
        :raise NotEmpty: if a timeout is set, and the buffer is not emptied in time
        """
