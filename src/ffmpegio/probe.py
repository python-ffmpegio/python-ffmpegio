import json, fractions
from . import ffmpeg


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
                    return v

    return {k: try_conv(v) for k, v in d.items()}


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

    args = ["-of", "json"]

    if select_streams:
        args.extend(["-select_streams", select_streams])

    modes = dict(
        format=show_format,
        stream=show_streams,
        programs=show_programs,
        chapters=show_chapters,
    )

    entries = []
    for key, val in modes.items():
        if not isinstance(val, bool):
            entries.append(f"{key}={','.join(val)}")
        elif val:
            entries.append(key)
        else:
            entries.append(f"{key}=")

    args.append("-show_entries")
    args.append(":".join(entries))
    args.append(url)

    results = json.loads(ffmpeg.ffprobe(args))

    if not modes["stream"]:
        modes["streams"] = modes["stream"]
    for key, val in modes.items():
        if not val and key in results:
            del results[key]

    return _items_to_numeric(results)


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
        tb = eval(res.pop("time_base", "1"))
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


# -show_data
# -show_data_hash algorithm
# -show_error
# -show_packets
# -show_frames
# -show_log loglevel
# -count_frames
# -count_packets
# -read_intervals read_intervals
# -show_private_data, -private
# -show_program_version
# -show_library_versions
# -show_versions
# -show_pixel_formats
# -bitexact
