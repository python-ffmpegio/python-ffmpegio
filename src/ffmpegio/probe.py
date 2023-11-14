import json, fractions, os, pickle, re
from collections import OrderedDict
from .path import ffprobe, PIPE
from .utils import parse_stream_spec

# fmt:off
__all__ = ['full_details', 'format_basic', 'streams_basic',
'video_streams_basic', 'audio_streams_basic', 'query']
# fmt:on

# stores all the local queries during the session
# - key: path
# - value: (mtime, blob)
_db = OrderedDict()
_db_maxsize = 16


def _items_to_numeric(d):
    def try_conv(v):
        if isinstance(v, dict):
            return _items_to_numeric(v)
        elif isinstance(v, list):
            return [try_conv(e) for e in v]
        else:
            try:
                return int(v)
            except ValueError:
                try:
                    return float(v)
                except ValueError:
                    try:
                        return fractions.Fraction(v)
                    except:
                        return v

    return {k: try_conv(v) for k, v in d.items()}


def _add_select_streams(args, stream_specifier):
    if stream_specifier:
        args.extend(["-select_streams", stream_specifier])
    return args


def _add_show_entries(args, entries):
    arg = []
    for key, val in entries.items():
        if not isinstance(val, bool):
            arg.append(f"{key}={','.join(val)}")
        elif val:
            arg.append(key)

    args.append("-show_entries")
    args.append(":".join(arg))
    return args


def _add_read_intervals(args, intervals):
    """add -read_intervals option to ffprobe argumnets

    :param args: argument list under construction
    :type args: list[str]
    :param intervals: interval specification
    :type intervals: str, int, float, seq[str|float,str|int|float], dict, seq[dict]
    :return: same as args input
    :rtype: list[str]

    ffprobe will seek to the interval starting point and will continue reading from that.
    intervals argument can be specified in multiple ways to form the ffprobe argument:

    1) ``str`` - pass through the argument as-is to ffprobe
    2) ``int`` - read this numbers of packets to read from the beginning of the file
    3) ``float`` - read packets over this duration in seconds from the beginning of the file
    4) ``seq[str|float, str|int|float]`` - sets start and end points
       - start: str = as-is, float=starting time in seconds
       - end: str = as-is, int=offset in # of packets, float=offset in seconds
    5) ``dict`` - specifies start and end points with the following keys:
       - 'start'        - (str|float) start time
       - 'start_offset' - (str|float) start time offset from the previous read. Ignored if 'start' is present.
       - 'end'          - (str|float) end time
       - 'end_offset'   - (str|float|int) end time offset from the start time. Ignored if 'end' is present.
    6) - ``seq[dict]`` - specify multiple intervals

    """

    # INTERVAL  ::= [START|+START_OFFSET][%[END|+END_OFFSET]]
    # INTERVALS ::= INTERVAL[,INTERVALS]
    if intervals is None:
        return args

    def compose_time(t, is_end_offset):
        if isinstance(t, str):
            return str
        elif isinstance(t, float):
            return str(t)
        elif is_end_offset and isinstance(t, int):
            return f"#{t}"
        else:
            raise ValueError("unknown interval endpoint specification")

    def compose_dict(intv):
        s = ""
        try:
            s = compose_time(intv["start"], False)
        except:
            try:
                s = "+" + compose_time(intv["start_offset"], False)
            except:
                pass
        try:
            s += "%" + compose_time(intv["end"], False)
        except:
            try:
                s += "%+" + compose_time(intv["end_offset"], True)
            except:
                pass
        return s

    if not isinstance(intervals, str):
        try:
            if isinstance(intervals, dict):
                intervals = compose_dict(intervals)
            else:
                try:
                    # try to set duration
                    intervals = f"%+{compose_time(intervals, True)}"
                except:
                    n = len(intervals)
                    if n and isinstance(intervals[0], dict):
                        # multiple intervals
                        intervals = ",".join([compose_dict(intv) for intv in intervals])
                    else:
                        # (start, +end)
                        assert len(intervals) == 2
                        start = compose_time(intervals[0], False)
                        end = compose_time(intervals[1], True)
                        intervals = f"{start}%+{end}"
        except:
            raise ValueError("unknown interval specification")

    args.extend(("-read_intervals", intervals))
    return args


def _exec(
    url, entries, streams=None, intervals=None, count_frames=False, count_packets=False
):
    """execute ffprobe and return data as dict"""

    sp_opts = {
        "stdout": PIPE,
        "stderr": PIPE,
        "universal_newlines": True,
        "encoding": "utf-8",
    }

    args = ["-hide_banner", "-of", "json"]

    if streams is not None:
        _add_select_streams(args, streams)

    if intervals is not None:
        _add_read_intervals(args, intervals)

    if count_frames:
        args.append("-count_frames")
        # returns "nb_read_frames" item in each stream

    if count_packets:
        args.append("-count_packets")
        # returns "nb_read_packets" item in each stream

    _add_show_entries(args, entries)

    pipe = not isinstance(url, str)
    args.append("-" if pipe else url)

    if pipe:
        try:
            assert url.seekable
            pos0 = url.tell()
            sp_opts["input"] = url
        except:
            raise ValueError("url must be str or seekable file-like object")

    # run ffprobe
    ret = ffprobe(args, **sp_opts)
    if ret.returncode != 0:
        raise Exception(f"ffprobe execution failed\n\n{ret.stderr}\n")

    # decode output JSON string
    results = json.loads(ret.stdout)

    if pipe:
        url.seek(pos0)
    return results


def _full_details(
    url,
    show_format=True,
    show_streams=True,
    show_programs=False,
    show_chapters=False,
    select_streams=None,
):
    """Retrieve full details of a media file or stream

    :param url: URL of the media file/stream
    :type url: str
    :param show_format: True to return format info, defaults to True
    :type show_format: bool, optional
    :param show_streams: True to return stream info, defaults to True
    :type show_streams: bool, optional
    :param show_programs: True to return program info, defaults to False
    :type show_programs: bool, optional
    :param show_chapters: True to return chapter info, defaults to False
    :type show_chapters: bool, optional
    :param select_streams: Indices of streams to get info of, defaults to None
    :type select_streams: seq of int, optional
    :return: media file information
    :rtype: dict

    """

    modes = dict(
        format=show_format,
        stream=show_streams,
        program=show_programs,
        chapter=show_chapters,
    )

    results = _exec(url, modes, select_streams)

    if not modes["stream"]:
        modes["streams"] = modes["stream"]
    for key, val in modes.items():
        if not val and key in results:
            del results[key]

    return _items_to_numeric(results)


def full_details(
    url,
    show_format=True,
    show_streams=True,
    show_programs=False,
    show_chapters=False,
    select_streams=None,
):
    """Retrieve full details of a media file or stream

    :param url: URL of the media file/stream
    :type url: str
    :param show_format: True to return format info, defaults to True
    :type show_format: bool, optional
    :param show_streams: True to return stream info, defaults to True
    :type show_streams: bool, optional
    :param show_programs: True to return program info, defaults to False
    :type show_programs: bool, optional
    :param show_chapters: True to return chapter info, defaults to False
    :type show_chapters: bool, optional
    :param select_streams: Indices of streams to get info of, defaults to None
    :type select_streams: seq of int, optional
    :return: media file information
    :rtype: dict

    """

    def _queryall_if_path():

        assert isinstance(url, str)

        sspec = None
        if select_streams is not None:
            try:
                sspec = (None, int(select_streams))
            except:
                m = re.match("([avstd])(?::([0-9]+))?$", select_streams)
                sspec = (
                    {
                        "a": "audio",
                        "v": "video",
                        "s": "subtitle",
                        "t": "attachment",
                        "d": "data",
                    }[m[1]],
                    m[2] and int(m[2]),
                )
                # raises exception if match not found

        mtime = os.stat(url).st_mtime
        db_entry = _db.get(url, None)
        if db_entry and db_entry[0] == mtime:
            _db.move_to_end(url, True)  # refresh the entry position
            results = pickle.loads(db_entry[1])
        else:
            results = _full_details(url, True, True, True, True)
            _db[url] = (mtime, pickle.dumps(results))
            if len(_db) > _db_maxsize:
                _db.popitem(False)  # remove the oldest entry

        # drop unrequested items
        for show, key in zip(
            (show_format, show_streams, show_programs, show_chapters),
            ("format", "streams", "programs", "chapters"),
        ):
            if not show:
                del results[key]

        # pick streams if specified
        if sspec is not None:
            t, i = sspec
            streams = results["streams"]
            if t is not None:
                streams = [st for st in streams if st["codec_type"] == t]
            if i is not None:
                streams = streams[i : i + 1]
            results["streams"] = streams

        return results

    if not show_streams:
        select_streams = None

    # get full query if url is a path
    try:
        return _queryall_if_path()
    except:
        return _full_details(
            url, show_format, show_streams, show_programs, show_chapters, select_streams
        )


def _resolve_entries(info_type, entries, default_entries, default_dep_entries={}):

    query = set(default_entries)

    if entries:
        user_query = set(entries)
        bad_query = user_query - query
        if bad_query:
            raise Exception(f"invalid {info_type} entries: {', '.join(bad_query)}")
        query = user_query

    for dent, dee in default_dep_entries.items():
        if dent in query:
            query.discard(dent)
            query |= set(dee)

    return query


def format_basic(url, entries=None):
    """Retrieve basic media format info

    :param url: URL of the media file/stream
    :type url: str
    :param entries: specify to narrow which information entries to retrieve. Default to None, to return all entries
    :type entries: seq of str
    :return: set of media format information.
    :rtype: dict


    Media Format Information Entries

    ===========  =====
    name         type
    ===========  =====
    filename     int
    nb_streams   str
    format_name  str
    start_time   float
    duration     float
    ===========  =====

    """

    default_entries = (
        "filename",
        "nb_streams",
        "format_name",
        "start_time",
        "duration",
    )

    results = full_details(
        url,
        show_format=_resolve_entries("basic format", entries, default_entries),
        show_streams=False,
    )["format"]
    return results


def streams_basic(url, entries=None):
    """Retrieve basic info of media streams

    :param url: URL of the media file/stream
    :type url: str
    :param entries: specify to narrow which stream entries to retrieve. Default to None, returning all entries
    :type entries: seq of str, optional
    :return: List of media stream information.
    :rtype: list of dict

    Media Stream Information dict Entries

    ==========   ====
    name         type
    ==========   ====
    index        int
    codec_name   str
    codec_type   str
    ==========   ====

    """

    default_entries = ("index", "codec_name", "codec_type")

    results = full_details(
        url,
        show_format=False,
        show_streams=_resolve_entries("basic streams", entries, default_entries),
    )["streams"]
    return results


def video_streams_basic(url, index=None, entries=None):
    """Retrieve basic info of video streams

    :param url: URL of the media file/stream
    :type url: str
    :param index: video stream index. 0=first video stream. Defaults to None, which returns info of all video streams
    :type index: int, optional
    :param entries: specify to narrow which information entries to retrieve. Default to None, to return all entries
    :type entries: seq of str
    :return: List of video stream information.
    :rtype: list of dict


    Video Stream Information Entries

    ====================  =========
    name                  type
    ====================  =========
    index                 int
    codec_name            str
    width                 int
    height                int
    sample_aspect_ratio   Fractions
    display_aspect_ratio  Fractions
    pix_fmt               str
    start_time            float
    duration              float
    frame_rate            Fractions
    nb_frames             int
    ====================  =========

    """

    default_entries = (
        "index",
        "codec_name",
        "width",
        "height",
        "sample_aspect_ratio",
        "display_aspect_ratio",
        "pix_fmt",
        "start_time",
        "duration",
        "frame_rate",
        "nb_frames",
    )

    durpara = ("duration_ts", "time_base")
    fspara = ("avg_frame_rate", "r_frame_rate")
    default_dep_entries = dict(
        start_time=("start_pts", "time_base"),
        duration=durpara,
        frame_rate=fspara,
        nb_frames=("nb_frames", *durpara, *fspara),
    )

    results = full_details(
        url,
        show_format=False,
        show_streams=_resolve_entries(
            "basic video", entries, default_entries, default_dep_entries
        ),
        select_streams=f"v:{index}" if index else "v",
    )["streams"]

    def adjust(res):
        tb = fractions.Fraction(res.pop("time_base", "1"))
        if "start_pts" in res:
            res["start_time"] = float(res.pop("start_pts", 0) * tb)

        duration = (
            float(res.pop("duration_ts", 0) * tb)
            if not entries or "duration" in entries or "nb_frames" in entries
            else None
        )
        if not entries or "duration" in entries:
            res["duration"] = duration

        fsa = res.pop("avg_frame_rate", "")
        fsr = res.pop("r_frame_rate", "0")
        frame_rate = fractions.Fraction(fsa if fsa and fsa != "0/0" else fsr)
        if not entries or "frame_rate" in entries:
            res["frame_rate"] = frame_rate

        if "sample_aspect_ratio" in res:
            res["sample_aspect_ratio"] = fractions.Fraction(
                res["sample_aspect_ratio"].replace(":", "/")
            )
        if "display_aspect_ratio" in res:
            res["display_aspect_ratio"] = fractions.Fraction(
                res["display_aspect_ratio"].replace(":", "/")
            )
        if "nb_frames" not in res and entries and "nb_frames" in entries:
            res["nb_frames"] = int(round(duration * frame_rate))

        return res

    return [adjust(r) for r in results]


def audio_streams_basic(url, index=None, entries=None):
    """Retrieve basic info of audio streams

    :param url: URL of the media file/stream
    :type url: str
    :param index: audio stream index. 0=first audio stream. Defaults to None, which returns info of all audio streams
    :type index: int, optional
    :param entries: specify to narrow which information entries to retrieve. Default to None, to return all entries
    :type entries: seq of str
    :return: List of audio stream information.
    :rtype: list of dict

    Audio Stream Information Entries

        ==============  =====
        name            type
        ==============  =====
        index           int
        codec_name      str
        sample_fmt      str
        sample_rate     int
        channels        int
        channel_layout  str
        start_time      float
        duration        float
        nb_samples      int
        ==============  =====

    """

    default_entries = (
        "index",
        "codec_name",
        "sample_fmt",
        "sample_rate",
        "channels",
        "channel_layout",
        "start_time",
        "duration",
        "nb_samples",
    )

    durpara = ("duration_ts", "time_base")
    default_dep_entries = dict(
        start_time=("start_pts", "time_base"),
        duration=durpara,
        nb_samples=("sample_rate", *durpara),
    )

    results = full_details(
        url,
        show_format=False,
        show_streams=_resolve_entries(
            "basic audio", entries, default_entries, default_dep_entries
        ),
        select_streams=f"a:{index}" if index else "a",
    )["streams"]

    def adjust(res):
        tb = res.pop("time_base", 1)
        start_pts = res.pop("start_pts", 0)
        duration_ts = res.pop("duration_ts", 0)

        if not entries or "start_time" in entries:
            res["start_time"] = start_pts * tb
        if not entries or "duration" in entries:
            res["duration"] = duration_ts * tb
        if (not entries or "nb_samples" in entries) and "nb_samples" not in res:
            res["nb_samples"] = int(round(duration_ts * tb * res["sample_rate"]))
            if entries and "sample_rate" not in entries:
                res.pop("sample_rate")

        return res

    return [adjust(r) for r in results]


def query(url, streams=None, fields=None, return_none=False):
    """Query specific fields of media format or streams

    :param url: URL of the media file/stream
    :type url: str
    :param streams: stream specifier, defaults to None to get format
    :type streams: str or int, optional
    :param fields: info, defaults to None
    :type fields: sequence of str, optional
    :param return_none: True to return an invalid field in the returned dict with None as its value
    :type return_none: bool, optional
    :return: field name-value dict. If streams argument is given but does not specify
             index, a list of dict is returned instead
    :rtype: dict or list or dict

    Note: Unlike :py:func:`video_stream_basic()` and :py:func:`audio_stream_basic()`,
          :py:func:`query()` does not process ffprobe output except for the conversion
          from str to float/int.

    """

    get_stream = streams is not None

    # check if full details are already available
    info = _db.get(url, None)

    if info is not None:
        # decode the info
        mtime = os.stat(url).st_mtime
        if info[0] == mtime:
            info = pickle.loads(info[1])

    do_query = info is None

    if do_query:  # if not run ffprobe
        info = (
            full_details(
                url,
                show_format=not get_stream,
                show_streams=get_stream,
                select_streams=streams,
            )
            if fields is None
            else _exec(
                url, {"format" if streams is None else "stream": fields}, streams
            )
        )

    info = info["streams" if get_stream else "format"]

    if get_stream and len(info) == 0:
        raise ValueError(f"Unknown or invalid stream specifier: {streams}")

    if get_stream and "index" in parse_stream_spec(streams):
        # return dict only if a specific stream requested
        info = info[0]

    if not do_query and fields is not None:
        # has full details from db, only return requested fields
        if isinstance(info, dict):
            info = {f: info[f] for f in fields if f in info}
        else:
            info = [{f: st[f] for f in fields if f in st} for st in info]

    if return_none:
        info = (
            {f: info.get(f, None) for f in fields}
            if isinstance(info, dict)
            else [{f: st.get(f, None) for f in fields} for st in info]
        )

    return info


def frames(url, entries=None, streams=None, intervals=None, accurate_time=False):
    """get frame information

    :param url: URL of the media file/stream
    :type url: str or seekable file-like object
    :param entries: names of frame attributes, defaults to None (get all attributes)
    :type entries: str or seq[str], optional
    :param stream: stream specifier of the stream to retrieve the data of, defaults to None to get all streams
    :type stream: str or int, optional
    :param intervals: time intervals to retrieve the data, see below for the details, defaults to None (get all)
    :type intervals: str, int, float, seq[str|float,str|int|float], dict, seq[dict]
    :param accurate_time: True to return all '\*_time' attributes to be computed from associated timestamps and
                          stream timebase, defaults to False (= us accuracy)
    :param accurate_time: bool, optional
    :return: frame information. list of dictionary if entries is None or a sequence; list of the selected entry
             if entries is str (i.e., a single entry)
    :rtype: list[dict] or list[str|int|float]

    ``intervals`` argument
    ----------------------

    intervals argument can be specified in multiple ways to form the ``-read_intervals`` ffprobe option:

    1) ``str`` - pass through the argument as-is to ffprobe
    2) ``int`` - read this numbers of packets to read from the beginning of the file
    3) ``float`` - read packets over this duration in seconds from the beginning of the file
    4) ``seq[str|float, str|int|float]`` - sets start and end points
       - start: str = as-is, float=starting time in seconds
       - end: str = as-is, int=offset in # of packets, float=offset in seconds
    5) ``dict`` - specifies start and end points with the following keys:
       - 'start'        - (str|float) start time
       - 'start_offset' - (str|float) start time offset from the previous read. Ignored if 'start' is present.
       - 'end'          - (str|float) end time
       - 'end_offset'   - (str|float|int) end time offset from the start time. Ignored if 'end' is present.
    6) - ``seq[dict]``  - specify multiple intervals

    """

    is_single = isinstance(entries, str)
    if is_single:
        entry = entries
        entries = [entries]

    pick_entries = entries is not None

    if accurate_time:
        has_time = not pick_entries
        if pick_entries:
            time_entries = []
            other_entries = set(("stream_index",))
            for e in entries:
                if e.endswith("_time"):
                    has_time = True
                    time_entries.append(e)
                    other_entries.add(e[:-5])
                else:
                    other_entries.add(e)
            if has_time:
                orig_entries = entries
                entries = other_entries

    entries = {"frame": (entries is None) or entries}
    if accurate_time and has_time:
        entries["stream"] = ["index", "time_base"]

    res = _exec(
        url,
        entries,
        streams=streams,
        intervals=intervals,
    )

    out = [_items_to_numeric(d) for d in res["frames"]]

    if len(out) == 0:
        return out

    if pick_entries and "side_data_list" not in entries["frame"]:
        # make sure side_data_list is not included
        for d in out:
            try:
                del d["side_data_list"]
            except KeyError:
                pass

    if accurate_time and has_time:

        time_bases = {
            d["index"]: fractions.Fraction(d["time_base"]) for d in res["streams"]
        }

        if not pick_entries:
            time_entries = [e for e in out[0].keys() if e.endswith("_time")]

        ts_entries = [e[:-5] for e in time_entries]

        for d in out:
            tb = time_bases[d["stream_index"]]
            for e, e_ts in zip(time_entries, ts_entries):
                d[e] = d[e_ts] * tb
                if pick_entries and e_ts not in orig_entries:
                    del d[e_ts]

    try:
        return [d[entry] for d in out] if is_single else out
    except:
        raise ValueError(f"invalid frame attribute: {entry}")
