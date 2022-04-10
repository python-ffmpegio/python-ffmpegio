"""media analysis tools module

"""

from collections import namedtuple
from .utils.filter import FilterGraph
from .utils.error import FFmpegError
from .threading import ProgressMonitorThread
from .path import ffmpeg, DEVNULL, PIPE, devnull
import re

from typing import Any, Protocol, Literal, Tuple


class MetadataLogger(Protocol):
    media_type: Literal["video", "audio"]  # the stream media type
    meta_names: Tuple[str]  # metadata names to be logged
    filter_name: str  # name of the FFmpeg filter to use
    options: dict[str, Any]  # FFmpeg filter options (value must be stringifiable)

    @property
    def filter_spec(self) -> str or Tuple:
        """filter specification expression to be used in FilterGraph"""
        ...

    @property
    def output(self) -> namedtuple:
        """output named tuple"""
        ...

    def log(self, name: str, key: str or None, value: str):
        """log the metadata

        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str
        """
        ...


def run(
    url,
    *loggers,
    time_units=None,
    start_at_zero=False,
    progress=None,
    show_log=None,
    **input_options,
):
    """analyze media streams' frames with lavfi filters

    :param url: video file url
    :type url: str
    :param \*loggers: class object with the metadata logging interface
    :type \*loggers: MetadataLogger
    :param ss: start time to process, defaults to None
    :type ss: int, float, str, optional
    :param t: duration of data to process, defaults to None
    :type t: int, float, str, optional
    :param to: stop processing at this time (ignored if t is also specified), defaults to None
    :type to: int, float, str, optional
    :param time_units: units of detected time stamps (not for ss, t, or to), defaults to None ('seconds')
    :type time_units: 'seconds', 'frames', 'pts', optional
    :param start_at_zero: ignore start time, defaults to False
    :type start_at_zero: bool, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
    :type show_log: bool, optional
    :param \**options: FFmpeg detector filter options. For a single-feature call, the FFmpeg filter options
        of the specified feature can be specified directly as keyword arguments. For a multiple-feature call,
        options for each individual FFmpeg filter can be specified with <feature>_options dict keyword argument.
        Any other arguments are treated as a common option to all FFmpeg filters. For the available options
        for each filter, follow the link on the feature table above to the FFmpeg documentation.
    :type \**options: dict, optional

    """

    if not len(loggers):
        raise ValueError("At least one logger object must be present.")

    try:
        tunits = ("frames", "pts", "seconds").index(time_units) + 1 if time_units else 3
    except:
        raise ValueError(
            f'time_units "{time_units}" is invalid. Must be one of ("frames", "pts", "seconds")'
        )

    filtspecs = {"video": [], "audio": []}
    for l in loggers:
        filtspecs[l.media_type].append(l.filter_spec)

    def create_fg(filtchain, metadata):
        return (
            FilterGraph(
                [[*filtchain, (metadata, "print", {"file": "-", "direct": True})]]
            )
            if len(filtchain)
            else None
        )

    vf, af = (
        create_fg(filtspecs[mediatype], metadata)
        for mediatype, metadata in zip(("video", "audio"), ("metadata", "ametadata"))
    )

    progmon = ProgressMonitorThread(progress)

    # create FFmpeg arguments
    args = ["-hide_banner"]
    if progress:
        args.extend("-progress", progmon.url)
    for k, v in input_options.items():
        args.extend((f"-{k}", str(v)))
    args.extend(("-i", str(url), "-copyts"))
    if start_at_zero:
        args.append("-start_at_zero")
    if vf:
        args.extend(("-vf", str(vf)))
    if af:
        args.extend(("-af", str(af)))
    args.extend(("-f", "null", devnull))

    # run FFmpeg
    with progmon:
        out = ffmpeg(
            args,
            stdout=PIPE,
            stderr=None if show_log else PIPE,
            universal_newlines=True,
        )
    # if FFmpeg terminated abnormally, return error
    if out.returncode:
        raise FFmpegError(out.stderr, show_log)

    # stdout analysis

    # link a logger to each metadata field names (trailing "lavifi.")
    meta_logger = {name: l for l in loggers for name in l.meta_names}

    re_metadata = re.compile(r"lavfi\.(.+?)(?:\.(.+?))?=(.+)")
    for m in re.finditer(
        r"frame:(\d+)\s+pts:(\d+)\s+pts_time:(\d+(?:\.\d+)?)\s*\n(.+?)(?=\nframe:|$)",
        out.stdout,
        re.DOTALL,
    ):
        # logged time
        t = (int, int, float)[tunits - 1](m[tunits])

        # log each meta data
        for mm in re_metadata.finditer(m[4]):
            try:
                meta_logger[mm[1]].log(t, *mm.groups())
            except:
                pass # ignore unknown metadata

    # return the loggers as convenience
    return loggers


class ScDet:
    media_type = "video"  # the stream media type
    meta_names = ("scd",)  # metadata primary names
    filter_name = "scdet"
    Output = namedtuple("Scenes", ["time", "score", "mafd"])
    OutputAll = namedtuple("AllSceneScores", ["time", "changed", "score", "mafd"])

    def __init__(self, all_scores=False, **options) -> None:
        self.all_scores = all_scores  #:bool: True to output scores of all frames
        self.options = options
        self.data = {}

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, _, key, value):
        if key == "mafd":  # always the first entry / frame
            self.data[t] = {"mafd": float(value)}
        elif key == "score":
            self.data[t]["score"] = float(value)
        elif key == "time":
            self.data[t]["changed"] = True

    @property
    def output(self):
        d = self.data
        if self.all_scores:
            times = sorted((t for t, v in self.data.items()))
            return self.OutputAll(
                times,
                *zip(
                    *(
                        (d[t].get("changed", False), d[t]["score"], d[t]["mafd"])
                        for t in times
                    )
                ),
            )
        else:
            times = sorted((t for t, v in d.items() if v.get("changed", False)))
            return self.Output(
                times, *zip(*((d[t]["score"], d[t]["mafd"]) for t in times))
            )


class BlackDetect:
    media_type = "video"  # the stream media type
    meta_names = ("black_start", "black_end")  # metadata primary names
    filter_name = "blackdetect"
    Output = namedtuple("Black", ["interval"])

    def __init__(self, **options):
        self.options = options
        self.interval = []

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, key, *_):
        if key == "black_start":
            self.interval.append([t, None])
        elif len(self.interval):
            self.interval[-1][-1] = t
        else:
            self.interval.append([None, t])

    @property
    def output(self):
        return self.Output(self.interval)


class BlackFrame:
    media_type = "video"  # the stream media type
    meta_names = ("blackframe",)  # metadata primary names
    filter_name = "blackframe"
    Output = namedtuple("BlackFrames", ["time", "pblack"])

    def __init__(self, **options):
        self.options = options
        self.frames = []

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, _, key, value):
        if key != "pblack":
            raise ValueError(f"Unknown blackframe metadata found: {key}")
        self.frames.append((t, int(value)))

    @property
    def output(self):
        return self.Output(*zip(*self.frames))


class FreezeDetect:
    media_type = "video"  # the stream media type
    meta_names = ("freeze",)  # metadata primary names
    filter_name = "freezedetect"
    Output = namedtuple("Frozen", ["interval"])

    def __init__(self, **options):
        self.options = options
        self.interval = []

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, _, key, __):
        if key == "freeze_start":
            self.interval.append([t, None])
        elif key == '"freeze_end"':
            if len(self.interval):
                self.interval[-1][-1] = t
            else:
                self.interval.append([None, t])

    @property
    def output(self):
        return self.Output(self.interval)


class SilenceDetect:
    media_type = "audio"  # the stream media type
    meta_names = ("silence_start", "silence_end")  # metadata primary names
    filter_name = "silencedetect"
    Output = namedtuple("Silent", ["interval"])

    def __init__(self, **options):
        self.options = options
        self.interval = []
        self.mono_intervals = {}  # mono intervals

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, key, ch, _):

        if ch is None:
            i = self.interval
        else:
            ch = int(ch) - 1
            try:
                i = self.mono_intervals[ch]
            except:
                i = self.mono_intervals[ch] = []

        if key == "silence_start":
            i.append([t, None])
        elif len(i):
            i[-1][-1] = t
        else:
            i.append([None, t])

    @property
    def output(self):
        nch = len(self.mono_intervals)
        if nch:
            channels = sorted(self.mono_intervals.keys())
            ints = [self.mono_intervals[ch] for ch in channels]
            return namedtuple("SilentIntervals", [f"ch{ch}" for ch in channels])(*ints)
        else:
            return self.Output(self.interval)

