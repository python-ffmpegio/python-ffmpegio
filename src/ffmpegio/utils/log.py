import re
import time
from . import layout_to_channels
from ..caps import sample_fmts
from fractions import Fraction


class ThreadNotActive(RuntimeError):
    pass


class FFmpegError(RuntimeError):
    def __init__(self, logs=None, log_shown=None):
        if logs is not None:
            if isinstance(logs,str):
                logs = re.split(r"[\n\r]+", logs)
            log = next((x for x in reversed(logs) if x.startswith("[")), None)
            nl = "\n"
            super().__init__(
                f"FFmpeg failed with unknown error:\n{nl.join(logs)}"
                if log is None
                else log
            )

        # File '...' already exists. Exiting.

        # ...: No such file or directory

        # Unrecognized option '...'.
        # Error splitting the argument list: Option not found

        # [AVFilterGraph @ 000002108e25d040] No such filter: '...'

        # Invalid duration specification for ss: 1001/15000

        elif log_shown:
            super().__init__("FFmpeg failed. Check its log printed above.")
        else:
            super().__init__(
                "FFmpeg failed with an unknown error. Set show_log=True or None to see the error."
            )


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
    if isinstance(logs,str):
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


from threading import Thread as _Thread, Condition as _Condition, Lock as _Lock
from io import TextIOBase as _TextIOBase, TextIOWrapper as _TextIOWrapper


class Logger(_Thread):
    def __init__(self, stderr, echo=False) -> None:
        self.stderr = stderr
        self.logs = []
        self._newline_mutex = _Lock()
        self.newline = _Condition(self._newline_mutex)
        self.echo = echo
        super().__init__()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stderr.close()
        self.join()  # will wait until stderr is closed
        return self

    def run(self):
        stderr = self.stderr
        if not isinstance(stderr, _TextIOBase):
            stderr = self.stderr = _TextIOWrapper(stderr, "utf-8")
        while True:
            try:
                log = stderr.readline()
            except:
                # stderr stream closed/FFmpeg terminated, end the thread as well
                break
            if not log and stderr.closed:
                break

            log = log[:-1]  # remove the newline

            if not log:
                time.sleep(0.001)
                continue

            if self.echo:
                print(log)

            with self.newline:
                self.logs.append(log)
                self.newline.notify_all()

        with self.newline:
            self.stderr = None
            self.newline.notify_all()

    def index(self, prefix, start=None, block=True, timeout=None):
        start = int(start or 0)
        with self.newline:
            logs = self.logs[start:] if start else self.logs
            try:
                # check existing lines
                return (
                    next((i for i, log in enumerate(logs) if log.startswith(prefix)))
                    + start
                )
            except:
                if not self.is_alive():
                    raise ThreadNotActive("Logger is not running")

                # no wait mode
                if not block:
                    raise ValueError("Specified line not found")

                # wait till matching line is read by the thread
                if timeout is not None:
                    timeout = time.time + timeout
                start = len(self.logs)
                while True:
                    # wait till the next log update
                    if not self.newline.wait(
                        timeout if timeout is None else timeout - time.time
                    ):
                        raise TimeoutError("Specified line not found")

                    # FFmpeg could have been terminated without match
                    if self.stderr is None:
                        raise ValueError("Specified line not found")

                    # check the new lines
                    try:
                        return (
                            next(
                                (
                                    i
                                    for i, log in enumerate(self.logs[start:])
                                    if log.startswith(prefix)
                                )
                            )
                            + start
                        )
                    except:
                        # still no match, update the starting position
                        start = len(self.logs)

    def output_stream(self, file_id=0, stream_id=0, block=True, timeout=None):
        try:
            i = self.index(f"Output #{file_id}", block=block, timeout=timeout)
            self.index(f"  Stream #{file_id}:{stream_id}", i, block, timeout)
        except ThreadNotActive as e:
            raise e
        except TimeoutError:
            raise TimeoutError("Specified output stream not found")
        except:
            raise ValueError("Specified output stream not found")

        with self._newline_mutex:
            return extract_output_stream(self.logs, hint=i)

    @property
    def Exception(self):
        return FFmpegError(self.logs)
