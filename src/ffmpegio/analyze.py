"""media analysis tools module

"""

from __future__ import annotations
from collections import namedtuple
import logging
from . import configure
from .utils import pop_extra_options
from .utils.filter import FilterGraph, compose_filter
from .utils.error import FFmpegError
from .threading import ProgressMonitorThread
from .path import ffmpeg, DEVNULL, PIPE, devnull
from . import ffmpegprocess
import re
from json import loads

from typing import Any, Tuple

try:
    from typing import Literal, Protocol
except ImportError:
    from typing_extensions import Literal, Protocol


def loudnorm(
    url,
    i=None,
    lra=None,
    tp=None,
    offset=None,
    linear=None,
    dual_mono=None,
    af=None,
    progress=None,
    overwrite=None,
    return_stats=False,
    **options,
):
    """run analysis (first pass) of EBU R128 loudness normalization

    :param url: input url
    :type url: str
    :param i: integrated loudness target, defaults to None
    :type i: float, optional
    :param lra: loudness range target, defaults to None
    :type lra: float, optional
    :param tp: maximum true peak, defaults to None
    :type tp: float, optional
    :param offset: offset gain, defaults to None
    :type offset: float, optional
    :param linear: True to normalize by linearly scaling the source audio, False to normalize dynamically, defaults to None
    :type linear: bool, optional
    :param dual_mono: True to treat mono input files as "dual-mono", defaults to None
    :type dual_mono: bool, optional
    :param af: preceding filter chain, defaults to None
    :type af: str, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param return_stats: True to return stats instead of loudnorm options, defaults to False
    :type return_stats: bool, optional
    :return: second pass loudnorm filter spec str or analysis stats
    :rtype: str or dict
    """
    loudnorm_opts = {
        k: v
        for k, v in zip(
            ["i", "lra", "tp", "offset", "linear", "dual_mono"],
            [i, lra, tp, offset, linear, dual_mono],
        )
        if v is not None
    }

    loundness_f = compose_filter(
        "loudnorm",
        {**loudnorm_opts, "print_format": "json"},
    )

    if af:
        af += f",{loundness_f}"
    else:
        af = loundness_f

    args = configure.empty()
    configure.add_url(args, "input", url, options)
    configure.add_url(
        args,
        "output",
        devnull,
        {
            "af": af,
            "f": "null",
            "vn": None,
            "sn": None,
            "ar": "192k",
            "c:a": "pcm_f32le",
        },
    )

    log = ffmpegprocess.run(
        args,
        progress=progress,
        overwrite=overwrite,
        capture_log=True,
        universal_newlines=True,
    ).stderr

    stats = loads(log[re.search(r"\[Parsed_loudnorm_2 @ .+\] \n", log).end() :])

    if return_stats:
        return stats

    for k, src in (
        ("measured_i", "input_i"),
        ("measured_lra", "input_lra"),
        ("measured_tp", "input_tp"),
        ("measured_thresh", "input_thresh"),
    ):
        loudnorm_opts[k] = float(stats[src])

    return compose_filter("loudnorm", loudnorm_opts)


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
    def ref_in(self) -> str or None:
        """stream specifier for reference input url only if applicable"""
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
    references=None,
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
    :param references: reference input urls, defaults to None
    :type references: list of str
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

    if isinstance(references, str):
        references = [references]

    try:
        tunits = ("frames", "pts", "seconds").index(time_units) + 1 if time_units else 3
    except:
        raise ValueError(
            f'time_units "{time_units}" is invalid. Must be one of ("frames", "pts", "seconds")'
        )

    # filtspecs = [{"video": [], "audio": []}, {"video": [], "audio": []}]
    # for l in loggers:
    #     try:  # just logger (no reference src specified)
    #         ref = 0 if l.require_reference else None
    #     except:  # expect 2-element seq (logger, index to references)
    #         try:
    #             l, ref = l
    #         except:
    #             raise ValueError(
    #                 "Each logger argument must be either a logger instance alone or "
    #                 "a sequence of the instance and reference url index."
    #             )

    #     ref = f"{ref+1}:{l.media_type[0]}"if l.require_reference else None

    #     filtspecs[l.require_reference][l.media_type].append(l.filter_spec)

    # def create_fg(filtchain, metadata):
    #     return (
    #         FilterGraph(
    #             [[*filtchain, (metadata, "print", {"file": "-", "direct": True})]]
    #         )
    #         if len(filtchain)
    #         else None
    #     )

    # vf, af = (
    #     create_fg(filtspecs[mediatype], metadata)
    #     for mediatype, metadata in zip(("video", "audio"), ("metadata", "ametadata"))
    # )

    l = loggers[0]
    vf = af = None
    if l.media_type == "video":
        vf = compose_filter(*l.filter_spec) + ",metadata=print:file=-"
    else:
        af = compose_filter(*l.filter_spec) + ",ametadata=print:file=-"

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
                pass  # ignore unknown metadata

    # return the loggers as convenience
    return loggers


class ScDet:
    media_type = "video"  # the stream media type
    meta_names = ("scd",)  # metadata primary names
    filter_name = "scdet"
    require_reference = False
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
    require_reference = False
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
    require_reference = False
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
    require_reference = False
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


class BBox:
    media_type = "video"  # the stream media type
    meta_names = ("bbox",)  # metadata primary names
    filter_name = "bbox"
    require_reference = False
    Output = namedtuple("BBox", ["time", "position"])
    pos_keys = {"y1": 1, "w": 2, "h": 3}

    def __init__(self, **options):
        self.options = options
        self.time = []
        self.position = []

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, _, key, value):
        if key == "x1":
            self.time.append(t)
            self.position.append([int(value), 0, 0, 0])
        else:
            try:
                key = self.pos_keys[key]
                self.position[-1][key] = int(value)
            except:
                pass

    @property
    def output(self):
        return self.Output(self.time, self.position)


class BlurDetect:
    media_type = "video"  # the stream media type
    meta_names = ("blur",)  # metadata primary names
    filter_name = "blurdetect"
    require_reference = False
    Output = namedtuple("Blur", ["time", "blur"])

    def __init__(self, **options):
        self.options = options
        self.frames = []

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, key, _, value):
        if key != "blur":
            raise ValueError(f"Unknown blurdetect metadata found: {key}")
        self.frames.append((t, float(value)))

    @property
    def output(self):
        return self.Output(*zip(*self.frames))


#  'frame:26   pts:26026   pts_time:0.867533\n'
#  'lavfi.entropy.entropy.normal.Y=4.762884\n'
#  'lavfi.entropy.normalized_entropy.normal.Y=0.595360\n'
#  'lavfi.entropy.entropy.normal.U=4.609038\n'
#  'lavfi.entropy.normalized_entropy.normal.U=0.576130\n'
#  'lavfi.entropy.entropy.normal.V=4.532040\n'
#  'lavfi.entropy.normalized_entropy.normal.V=0.566505\n'
class PSNR:
    media_type = "video"  # the stream media type
    meta_names = ("psnr",)  # metadata primary names
    filter_name = "psnr"
    require_reference = True
    re_key = re.compile(r"(.+)(?:\.(.))?")

    def __init__(self, **options):
        self.options = options
        self.time = []
        self.comps = []
        self.stats = {}
        self._first = None

    @property
    def filter_spec(self):
        return (self.filter_name, self.options)

    def log(self, t, _, key, value):

        m = self.re_key.match(key)
        if not (m and m[1]):
            logging.warning(f"[PSNR.log()] Unknown metadata key: {key}")
            return

        if not self._first:
            self._first = key

        name, comp = m.groups()

        new_row = key == self._first
        if new_row:
            self.time.append(t)
        if comp:
            n = len(t)
            if n == 1:
                self.comps.append(comp)
            try:
                stat = self.stats[name]
            except:
                stat = self.stats[name] = []
            if len(stat) < n:
                l = []
                stat.append(l)
            else:
                l = stat[-1]
        else:
            try:
                l = self.stats[name]
            except:
                l = self.stats[name] = []

        l.append(float(value))

    @property
    def output(self):
        Output = namedtuple("PSNR", ["time", *self.stats.keys()])
        return Output(self.time, *self.stats.values())


class SilenceDetect:
    media_type = "audio"  # the stream media type
    meta_names = ("silence_start", "silence_end")  # metadata primary names
    filter_name = "silencedetect"
    require_reference = False
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


class APhaseMeter:
    media_type = "audio"  # the stream media type
    meta_names = ("aphasemeter",)  # metadata primary names
    filter_name = "aphasemeter"
    require_reference = False
    Output = namedtuple(
        "Phase", ["time", "value", "mono_interval", "out_phase_interval"]
    )

    def __init__(self, **options):
        self.options = options
        self.time = []
        self.value = []
        self.mono = []
        self.out_phase = []

    @property
    def filter_spec(self):
        return (self.filter_name, {**self.options, "video": False, "phasing": True})

    def log(self, t, _, key, val):

        if key == "phase":
            self.time.append(t)
            self.value.append(float(val))
        else:
            ptype, action = key.rsplit("_", 1)
            i = getattr(self, ptype)

            if action == ("start"):
                i.append([t, None])
            elif action == "end":
                if len(i):
                    i[-1][-1] = t
                else:
                    i.append([None, t])

    @property
    def output(self):
        return self.Output(self.time, self.value, self.mono, self.out_phase)


class AStats:
    media_type = "audio"  # the stream media type
    meta_names = ("astats",)  # metadata primary names
    filter_name = "astats"
    require_reference = False
    re_key = re.compile(
        r"(?:(\d+)|Overall)\.(.+)|(Number of NaNs|Number of Infs|Number of denormals)"
    )

    # fmt: off
    stats_names = {
        meas: meas.lower().replace(" ", "_")
        for meas in (
            "DC_offset", "Min_level", "Max_level", "Min_difference", "Max_difference",
            "Mean_difference", "RMS_difference", "Peak_level", "RMS_level", "RMS_peak",
            "RMS_trough", "Crest_factor", "Flat_factor", "Peak_count", "Noise_floor",
            "Noise_floor_count", "Entropy", "Bit_depth", "Bit_depth2", "Dynamic_range",
            "Zero_crossings", "Zero_crossings_rate", "Number of NaNs", "Number of Infs",
            "Number of denormals",
        )
    }
    # fmt: on
    Output = namedtuple("AStats", ["time", *stats_names.values()])

    def __init__(self, **options):
        self.options = options
        self.time = []
        self._first = None
        for meas in AStats.stats_names.values():
            setattr(self, meas, {})

    @property
    def filter_spec(self):
        return (self.filter_name, {**self.options, "metadata": True})

    def log(self, t, _, key, value):

        if not self._first:
            self._first = key

        if key == self._first:
            self.time.append(t)

        m = self.re_key.match(key)
        if not m:
            logging.warning(f"[AStats.log()] Unknown metadata key: {key}")
            return

        ch, name, bug = m.groups()
        ch = "overall" if ch is None else int(ch) - 1
        key = self.stats[bug or name]

        try:
            stat = self.stats[key]
        except:
            stat = self.stats[key] = {}

        try:
            l = stat[ch]
        except:
            l = stat[ch] = []

        l.append(float(value))

    @property
    def output(self):
        return self.Output(
            self.time,
            *(
                getattr(self, meas)
                for meas in AStats.stats_names.values()
                if hasattr(self, meas)
            ),
        )


class ASpectralStats:
    media_type = "audio"  # the stream media type
    meta_names = ("aspectralstats",)  # metadata primary names
    filter_name = "aspectralstats"
    require_reference = False
    re_key = re.compile(r"(?:(\d+)\.)?(.+)")

    def __init__(self, **options):
        self.options = options
        self.time = []
        self.stats = {}
        self._first = None

    @property
    def filter_spec(self):
        return (self.filter_name, {**self.options, "metadata": True})

    def log(self, t, _, key, value):

        m = self.re_key.match(key)
        if not (m and m[1]):
            logging.warning(f"[ASpectralStats.log()] Unknown metadata key: {key}")
            return

        if not self._first:
            self._first = key

        ch, name = m.groups()

        if key == self._first:
            self.time.append(t)

        try:
            stat = self.stats[name]
        except:
            stat = self.stats[name] = {}

        ch = int(ch) - 1
        try:
            l = stat[ch]
        except:
            l = stat[ch] = []

        l.append(float(value))

    @property
    def output(self):
        Output = namedtuple("ASpectralStats", ["time", *self.stats.keys()])
        return Output(self.time, *self.stats.values())
