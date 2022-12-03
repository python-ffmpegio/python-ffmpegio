"""media analysis tools module

"""

from __future__ import annotations
from collections import namedtuple
from abc import ABC
import logging
from . import configure
from .filtergraph import Graph, Filter, Chain, as_filtergraph
from .utils.filter import compose_filter
from .errors import FFmpegError
from .path import devnull
from . import ffmpegprocess as fp
import re
from json import loads

from typing import Any, Tuple, NamedTuple, List

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


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

    loundness_f = Filter("loudnorm", **loudnorm_opts, print_format="json")

    af = (Graph(af) + loundness_f) if af else loundness_f

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

    log = fp.run(
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


class MetadataLogger(ABC):
    media_type: Literal["video", "audio"]  # the stream media type
    meta_names: Tuple[str]  # metadata names to be logged
    filter_name: str  # name of the FFmpeg filter to use
    options: dict[str, Any]  # FFmpeg filter options (value must be stringifiable)

    @property
    def filter(self) -> Filter:
        """filter specification expression to be used in FilterGraph"""
        return Filter(self.filter_name, **self.options)

    @property
    def ref_in(self) -> str or None:
        """stream specifier for reference input url only if applicable"""
        return None

    @property
    def output(self) -> namedtuple:
        """output named tuple"""
        ...

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

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
    :param references: reference input urls or pairs of url and input option
                       dict, defaults to None
    :type references: seq of str or seq of (str, dict), optional
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

    if references is None:
        references = ()
    elif isinstance(references, str):
        references = [references]

    try:
        tunits = ("frames", "pts", "seconds").index(time_units) + 1 if time_units else 3
    except:
        raise ValueError(
            f'time_units "{time_units}" is invalid. Must be one of ("frames", "pts", "seconds")'
        )

    fchains = {"video": Chain([]), "audio": Chain([])}
    for l in loggers:
        # filterchain under consturction
        c = fchains[l.media_type]

        # logging filter (may need to convert to filtergraph if uses a reference stream)
        f = (
            l.filter
            if l.ref_in is None
            else Graph([l.filter], {l.ref_in: ((0, 0, 1), None)})
        )
        # if requires reference stream, make sure the fchain is a Graph object, too
        if l.ref_in and type(c) != Graph:
            fchains[l.media_type] = c = as_filtergraph(c)

        # assign the logger to get the output of the previous logger
        c >>= f

    if len(fchains["video"]):
        fchains["video"] >>= Filter("metadata", "print", file="-")

    if len(fchains["audio"]):
        fchains["audio"] >>= Filter("ametadata", "print", file="-")

    oopts = {"f": "null"}
    gopts = {"copyts": fp.FLAG}
    if start_at_zero:
        gopts["start_at_zero"] = fp.FLAG

    vf, af = fchains.values()
    if isinstance(vf, Graph) or isinstance(af, Graph):
        # at least one logger requires reference input, must use filter_complex
        if len(vf):
            vf = "[0:v:0]" >> vf >> "nullsink"
        if len(af):
            af = "[0:a:0]" >> af >> "anullsink"
        gopts["filter_complex"] = vf | af
    else:
        # set filter chains
        for k, fg in zip(("vf", "af"), fchains.values()):
            if len(fg):
                oopts[k] = fg

    # create FFmpeg arguments
    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url, input_options)
    for ref in references:
        if isinstance(ref, str):
            configure.add_url(ffmpeg_args, "input", ref)
        else:
            configure.add_url(ffmpeg_args, "input", *ref)
    configure.add_url(ffmpeg_args, "output", devnull, oopts)
    ffmpeg_args["global_options"] = gopts

    # run FFmpeg
    out = fp.run(
        ffmpeg_args,
        progress=progress,
        capture_log=True,
        universal_newlines=True,
        stdout=fp.PIPE,
        stderr=fp.PIPE if show_log else None,
    )

    # if FFmpeg terminated abnormally, return error
    if out.returncode:
        if show_log:
            print(out.stderr)
        raise FFmpegError(out.stderr, show_log)

    # link a logger to each metadata field names (trailing "lavifi.")
    meta_logger = {name: l for l in loggers for name in l.meta_names}

    # stdout analysis
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


class ScDet(MetadataLogger):
    class Scenes(NamedTuple):
        """Default output named tuple subclass"""

        time: Tuple[float | int]  #: log times
        score: Tuple[float]  #: scene change scores
        mafd: Tuple[float]  #: mafd scores

    class AllScenes(NamedTuple):
        """Output named tuple subclass for all_scores=True"""

        time: Tuple[float | int]  #: log times
        changed: Tuple[bool]  #: scene change flags
        score: Tuple[float]  #: scene change scores
        mafd: Tuple[float]  #: mafd scores
    filter_name = "scdet"

    def __init__(self, all_scores=False, **options) -> None:
        self.all_scores = all_scores  #:bool: True to output scores of all frames
        self.options = options
        self.data = {}

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """
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
            return self.AllScenes(
                tuple(times),
                *zip(
                    *(
                        (d[t].get("changed", False), d[t]["score"], d[t]["mafd"])
                        for t in times
                    )
                ),
            )
        else:
            times = sorted((t for t, v in d.items() if v.get("changed", False)))
            return self.Scenes(
                tuple(times), *zip(*((d[t]["score"], d[t]["mafd"]) for t in times))
            )


class BlackDetect(MetadataLogger):
    class Black(NamedTuple):
        """output log namedtuple subclass"""

        interval: List[
            float | int | None, float | int | None
        ]  #: pairs of start and end timestamps of black intervals
    filter_name = "blackdetect"

    def __init__(self, **options):
        self.options = options
        self.interval = []

    def log(self, t: float | int, name: str, *_):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: metadata key
        :type bane: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """
        if name == "black_start":
            self.interval.append([t, None])
        elif len(self.interval):
            self.interval[-1][-1] = t
        else:
            self.interval.append([None, t])

    @property
    def output(self) -> Black:
        return self.Black(self.interval)


class BlackFrame(MetadataLogger):
    media_type = "video"  # the stream media type
    meta_names = ("blackframe",)  # metadata primary names
    filter_name = "blackframe"

    class BlackFrames(NamedTuple):
        time: List[float | int]  #: timestamp in seconds, frames, or pts
        pblack: List[int]  #: percentage of black pixels

    def __init__(self, **options):
        self.options = options
        self.frames = []

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """
        if key != "pblack":
            raise ValueError(f"Unknown blackframe metadata found: {key}")
        self.frames.append((t, int(value)))

    @property
    def output(self) -> BlackFrames:
        """log output"""
        return self.BlackFrames(*zip(*self.frames))


class FreezeDetect(MetadataLogger):
    media_type = "video"  # the stream media type
    meta_names = ("freeze",)  # metadata primary names
    filter_name = "freezedetect"

    class Frozen(NamedTuple):
        """output log namedtuple subclass"""

        #: pairs of start and end timestamps of frozen frame intervals

    def __init__(self, **options):
        self.options = options
        self.interval = []

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """
        if key == "freeze_start":
            self.interval.append([t, None])
        elif key == '"freeze_end"':
            if len(self.interval):
                self.interval[-1][-1] = t
            else:
                self.interval.append([None, t])

    @property
    def output(self)->Frozen:
        return self.Frozen(self.interval)


class BBox(MetadataLogger):
    media_type = "video"  # the stream media type
    meta_names = ("bbox",)  # metadata primary names
    filter_name = "bbox"

    class BBox(NamedTuple):
        """output log namedtuple subclass"""

        time: List[float | int]  #: timestamp in seconds, frames, or pts
        position: List[List[int, int, int, int]]  #: bbox positions [x0,x1,w,h]

    pos_keys = {"y1": 1, "w": 2, "h": 3}

    def __init__(self, **options):
        self.options = options
        self.time = []
        self.position = []

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """
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
    def output(self) -> BBox:
        return self.BBox(self.time, self.position)

class BlurDetect(MetadataLogger):
    media_type = "video"  # the stream media type
    meta_names = ("blur",)  # metadata primary names
    filter_name = "blurdetect"

    class Blur(NamedTuple):
        """output log namedtuple subclass"""

        time: List[float | int]  #: timestamp in seconds, frames, or pts
        blur: List[float] #: blurness score

    def __init__(self, **options):
        self.options = options
        self.frames = []

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """
        if key != "blur":
            raise ValueError(f"Unknown blurdetect metadata found: {key}")
        self.frames.append((t, float(value)))

    @property
    def output(self)->BlurDetect.Blur:
        """log output"""
        return self.Blur(*zip(*self.frames))


#  'frame:26   pts:26026   pts_time:0.867533\n'
#  'lavfi.entropy.entropy.normal.Y=4.762884\n'
#  'lavfi.entropy.normalized_entropy.normal.Y=0.595360\n'
#  'lavfi.entropy.entropy.normal.U=4.609038\n'
#  'lavfi.entropy.normalized_entropy.normal.U=0.576130\n'
#  'lavfi.entropy.entropy.normal.V=4.532040\n'
#  'lavfi.entropy.normalized_entropy.normal.V=0.566505\n'
class PSNR(MetadataLogger):
    media_type = "video"  # the stream media type
    meta_names = ("psnr",)  # metadata primary names
    filter_name = "psnr"
    re_key = re.compile(r"(.+)(?:\.(.))?")

    def __init__(self, ref_stream_spec, **options):
        self.options = options
        self.time = []
        self.comps = []
        self.stats = {}
        self._first = None
        self._ref = ref_stream_spec

    @property
    def ref_in(self):
        return self._ref

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """

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


class SilenceDetect(MetadataLogger):
    media_type = "audio"  # the stream media type
    meta_names = ("silence_start", "silence_end")  # metadata primary names
    filter_name = "silencedetect"
    Output = namedtuple("Silent", ["interval"])

    def __init__(self, **options):
        self.options = options
        self.interval = []
        self.mono_intervals = {}  # mono intervals

    def log(self, t: float | int, name: str, ch: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param ch: audio channel key
        :type ch: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """

        if ch is None:
            i = self.interval
        else:
            ch = int(ch) - 1
            try:
                i = self.mono_intervals[ch]
            except:
                i = self.mono_intervals[ch] = []

        if name == "silence_start":
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


class APhaseMeter(MetadataLogger):
    media_type = "audio"  # the stream media type
    meta_names = ("aphasemeter",)  # metadata primary names
    filter_name = "aphasemeter"
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
    def filter(self):
        return Filter(self.filter_name, **self.options, video=False, phasing=True)

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """

        if key == "phase":
            self.time.append(t)
            self.value.append(float(value))
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


class AStats(MetadataLogger):
    media_type = "audio"  # the stream media type
    meta_names = ("astats",)  # metadata primary names
    filter_name = "astats"
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
    def filter(self):
        return Filter(self.filter_name, **self.options, metadata=True)

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """

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


class ASpectralStats(MetadataLogger):
    media_type = "audio"  # the stream media type
    meta_names = ("aspectralstats",)  # metadata primary names
    filter_name = "aspectralstats"
    re_key = re.compile(r"(?:(\d+)\.)?(.+)")

    def __init__(self, **options):
        self.options = options
        self.time = []
        self.stats = {}
        self._first = None

    def log(self, t: float | int, name: str, key: Optional[str], value: str):
        """log the metadata

        :param t: timestamp in seconds, frames, or pts
        :type t: float|int
        :param name: one of the class' meta_names
        :type name: str
        :param key: secondary metadata key if found
        :type key: str | None
        :param value: metadata value
        :type value: str

        This method is called by :py:func:`analyze.run` if a metadata line begins
        with one of the class' ``meta_names`` entry. The `log` method shall store
        the metadata info in a private storage property of the class so they can be
        returned later by the `output` property.

        """

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
