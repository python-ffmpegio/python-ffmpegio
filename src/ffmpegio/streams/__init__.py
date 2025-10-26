'''media streamer classes

    ==================== ===================== ====================
    Class Name           Input(s)              Output(s)
    ==================== ===================== ====================
    SimpleVideoReader    multiple urls         single video
    SimpleVideoWriter    single video          single url
    SimpleAudioReader    multiple urls         single audio
    SimpleAudioWriter    single audio          single url

    MediaReader          multiple urls/encoded multiple audio/video
    MediaWriter          multiple audio/video  multiple urls/encoded
    MediaTranscoder      multiple encoded      multiple encoded
    SISOMediaFilter      single audio/video    single audio/video
    MISOMediaFilter      multiple audio/video  single audio/video
    SIMOMediaFilter      single audio/video    multiple audio/video
    MIMOMediaFilter      multiple audio/video  multiple audio/video
    ==================== ====================  ====================
'''

from .SimpleStreams import (
    SimpleVideoReader,
    SimpleVideoWriter,
    SimpleAudioReader,
    SimpleAudioWriter
)
from .PipedStreams import (
    MediaReader,
    MediaWriter,
    MediaTranscoder,
    SISOMediaFilter,
    MISOMediaFilter,
    SIMOMediaFilter,
    MIMOMediaFilter,
)
from .AviStreams import AviMediaReader


# TODO multi-stream write
# TODO Buffered reverse video read

# fmt: off
__all__ = ["SimpleVideoReader", "SimpleVideoWriter", "SimpleAudioReader", "SimpleAudioWriter",
    "MediaReader", "MediaWriter", "MediaTranscoder",
    "SISOMediaFilter", "MISOMediaFilter", "SIMOMediaFilter", "MIMOMediaFilter"]
# fmt: on
