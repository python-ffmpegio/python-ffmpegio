"""media streamer classes

=============== ===================== ====================
Class Name           Input(s)              Output(s)
=============== ===================== ====================
SimpleReader    multiple urls         single audio/video
SimpleWriter    single audio/video    single url

MediaReader     multiple urls/encoded multiple audio/video
MediaWriter     multiple audio/video  multiple urls/encoded
MediaTranscoder multiple encoded      multiple encoded
SISOMediaFilter single audio/video    single audio/video
MISOMediaFilter multiple audio/video  single audio/video
SIMOMediaFilter single audio/video    multiple audio/video
MIMOMediaFilter multiple audio/video  multiple audio/video
=============== ====================  ====================
"""

from .SimpleStreams import SimpleReader, SimpleWriter
from .PipedStreams import (
    MediaReader,
    MediaWriter,
    MediaTranscoder,
    SISOMediaFilter,
    MISOMediaFilter,
    SIMOMediaFilter,
    MIMOMediaFilter,
)


# TODO multi-stream write
# TODO Buffered reverse video read

# fmt: off
__all__ = ["SimpleReader", "SimpleWriter",
    "MediaReader", "MediaWriter", "MediaTranscoder",
    "SISOMediaFilter", "MISOMediaFilter", "SIMOMediaFilter", "MIMOMediaFilter"]
# fmt: on
