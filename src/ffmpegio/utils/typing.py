from __future__ import annotations

from typing import *
from typing_extensions import *

# from typing_extensions import *

MediaType = Literal["v", "a", "s", "d", "t", "V"]
# libavformat/avformat.c:match_stream_specifier()


class StreamSpec_Options(TypedDict):
    media_type: MediaType  # py3.11 NotRequired[MediaType]
    file_index: int  # py3.11 NotRequired[int]
    program_id: int  # py3.11 NotRequired[int]
    group_index: int  # py3.11 NotRequired[int]
    group_id: int  # py3.11 NotRequired[int]
    stream_id: int  # py3.11 NotRequired[int]


class StreamSpec_Index(StreamSpec_Options):
    index: int


class StreamSpec_Tag(StreamSpec_Options):
    tag: Union[str, Tuple[str, str]]


class StreamSpec_Usable(StreamSpec_Options):
    usable: bool


StreamSpec = Union[StreamSpec_Index, StreamSpec_Tag, StreamSpec_Usable]
