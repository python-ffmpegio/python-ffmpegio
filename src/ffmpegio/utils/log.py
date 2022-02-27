import re
from fractions import Fraction

from . import layout_to_channels
from ..caps import sample_fmts

_re_audio = re.compile(r"(?:(\d+) Hz, )?(.+)")


def parse_log_audio_stream(info):
    """parse audio codec info on FFmpeg log

    :param info: stream info string after basic codec info
    :type info: str
    :return: dict containing stream info with keys matching FFmpeg options
    :rtype: dict

    Output Key    Type  Description
    ------------  ----  -------------------------------------
    'ar'          int   Sampling rate in samples/second
    'ac'          int   Number of audio channels
    'sample_fmt'  str   Audio sample format

    """

    mm = _re_audio.match(info)

    d = {}
    if mm[1]:
        d["ar"] = int(mm[1])
    items = mm[2].split(", ")

    i = 1
    if len(items):
        try:
            d["ac"] = layout_to_channels(items[0])
        except:
            try:
                d["ac"] = int(re.match(r"(\d+) channels", items[0])[1])
            except:
                i = 0

    sample_fmt = items[i] if len(items) > i else None
    if sample_fmt is not None:
        sample_fmt = sample_fmt.split(" ", 1)[0]
        if sample_fmt in sample_fmts():
            d["sample_fmt"] = sample_fmt
    return d


# none|pix_fmt[([%bits_per_raw_sample% bpc, ][%color_range%, ]
# [%color_space_name%/%color_primaries_name%/%color_transfer_name%, |%color_primaries_name%, ]
# [%field_order%, ][%chroma_sample_location%, ])]
# [[(??|, )%width%x%height%[ (coded_widthxcoded_height)][ \[SAR %d:%d DAR %d:%d\]][, %d/%d]]]
# [, q=%d-%d]|[, Closed Captions][, Film Grain][, lossless]

_re_video_codec = re.compile(
    r"(none)|([a-z0-9]+)(?:\(.+?\))?(?:, ([0-9]+)x([0-9]+)(?: [0-9]+x[0-9]+)?(?:, \[SAR [0-9]+:[0-9]+ DAR ([0-9]+):([0-9]+)\])?)?"
)


# [(avg_frame_rate) fps, (r_frame_rate) tbr, (1/time_base) tbn]
_re_video_fps = re.compile(r"([0-9.]+)(k)? fps|([0-9.]+)(k)? tbr")


def parse_log_video_stream(info):
    """parse video codec info in FFmpeg log

    :param info: stream info string after basic codec info
    :type info: str
    :return: dict containing stream info with keys matching FFmpeg options
    :rtype: dict

    Output Key    Type  Description
    ------------  ----  -------------------------------------
    'r'           int   Sampling rate in samples/second
    'pix_fmt'     str   Pixel format
    's'           [int, int] width and height
    'aspect'      Fraction display aspect ratio

    """
    d = {}
    mm = _re_video_codec.match(info)
    if mm[2]:
        d["pix_fmt"] = mm[2]
    if mm[3]:
        d["s"] = [int(mm[i]) for i in range(3, 5)]
        if mm[5]:
            d["aspect"] = Fraction(*[int(mm[i]) for i in range(5, 7)])

    mm = _re_video_fps.search(info, mm.end())
    r = None
    if mm[1]:
        r = float(mm[1])
        if mm[2]:
            r *= 1e3
    elif mm[3]:
        r = float(mm[3])
        if mm[4]:
            r *= 1e3
    if r is not None:
        ri = int(r)
        d["r"] = ri if ri == r else Fraction(round(r * 1001), 1001)
        # [TODO] x1001 is a hack job, revisit

    return d


_re_stream = re.compile(
    r"  Stream #\d+:\d+(?:\[.+?\])?(?:\(.+?\))?: (Audio|Video): ([^, ]+)(?: \(.+?\))*, (.*)"
)


def extract_output_stream(logs, file_id=0, stream_id=0, hint=None):
    """extract output stream info from the log lines

    :param logs: lines of FFmpeg log messages
    :type logs: seq(str)
    :param file_id: output file id, defaults to 0
    :type file_id: int, optional
    :param stream_id: output stream id, defaults to 0
    :type stream_id: int, optional
    :param hint: starting log line index to search, defaults to None
    :type hint: int, optional
    :return: stream information
    :rtype: dict
    """
    if isinstance(logs, str):
        logs = re.split(r"[\n\r]+", logs)
    fname = f"Output #{file_id}"
    sname = f"  Stream #{file_id}:{stream_id}"
    if hint:
        logs = logs[hint:]
    i0 = next((i for i, l in enumerate(logs) if l.startswith(fname)), None)
    if i0 is None:
        raise ValueError("output log is not present")
    log = next((l for l in logs[i0:] if l.startswith(sname)), None)
    if log is None:
        raise ValueError("output stream log is not present")

    # https://github.com/FFmpeg/FFmpeg/blob/6af21de373c979bc2087717acb61e834768ebe4b/libavformat/dump.c#L621
    # https://github.com/FFmpeg/FFmpeg/blob/cd03a180cb66ca199707ad129a4ab44548711c94/libavcodec/avcodec.c#L519

    sinfo = {}
    m = _re_stream.match(log)

    type = m[1]
    sinfo = {"codec": m[2], "type": type.lower()}
    info = m[3]
    if type == "Audio":
        sinfo = {**sinfo, **parse_log_audio_stream(info)}
    elif type == "Video":
        sinfo = {**sinfo, **parse_log_video_stream(info)}
    else:
        raise RuntimeError(f"parser for {type.lower()} codec is not defined.")

    return sinfo
