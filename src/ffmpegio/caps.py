# TODO add function to guess media type given extension

from __future__ import annotations

import fractions
import logging
import re
import subprocess as sp
from fractions import Fraction
from functools import cache, partial
from typing import Callable, Literal, LiteralString, NamedTuple, TypedDict, TypeVar

from .errors import FFmpegError, FFmpegioError
from .path import ffmpeg as _ffmpeg

logger = logging.getLogger("ffmpegio")

# fmt:off
__all__ = ["options", "filters", "codecs", "encoders", "decoders", "formats", 
    "devices", "muxers", "demuxers", "bsfilters", "protocols", "pix_fmts", 
    "sample_fmts", "layouts", "colors", "demuxer_info", "muxer_info", "encoder_info",
    "decoder_info", "filter_info", "bsfilter_info", "frame_rate_presets",
    "video_size_presets", "FilterInfo", "BSFInfo"]
# fmt:on

_ffCodecRegexp = re.compile(
    r"([D.])([E.])([VAS])([I.])([L.])([S.])\s+([^=\s][\S]*)\s+(.*)"
)  # g
_ffEncodersRegexp = re.compile(r"\s+\(encoders:([^\)]+)\)")
_ffDecodersRegexp = re.compile(r"\s+\(decoders:([^\)]+)\)")
_coderRegexp = re.compile(
    r"([VAS])([F.])([S.])([X.])([B.])([D.])\s+([^=\s]\S*)\s+(.*)"
)  # g
_formatRegexp = re.compile(r"([D ])([E ])([d ])? +(\S+) +(.*)")  # g
_filterRegexp = re.compile(
    r"([T.])([S.])([C.])?\s+(\S+)\s+(A+|V+|N|\|)->(A+|V+|N|\|)\s+(.*)"
)  # g


def ffmpeg(gopts: list[str]) -> str:
    out = _ffmpeg(["-hide_banner", *gopts], stdout=sp.PIPE, encoding="utf-8")

    if out.returncode:
        raise FFmpegError(out.stdout)

    return out.stdout


def _(
    # fmt:off
    cap: Literal[
        "formats",
        "muxers",
        "demuxers",
        "devices",
        "codecs",
        "decoders",
        "encoders",
        "filters",
        "pix_fmts",
        "layouts",
        "sample_fmts",
        "bsfs",
        "protocols",
        "dispositions",
        "colors",
        "hwaccels",
    ],
    # fmt:on
) -> str:
    return ffmpeg([f"-{cap}"])


def __(
    type: Literal[
        "decoder", "encoder", "demuxer", "muxer", "filter", "bsf", "protocol"
    ],
    name: str,
) -> str:
    return ffmpeg(["-help", f"{type}={name}"])


@cache
def _parse_options() -> dict[
    Literal[
        "per-file",
        "per-stream",
        "video",
        "audio",
        "subtitle",
        "general",
        "global",
    ],
    dict[str, str],
]:
    """parse output of `ffmpeg -help long`"""

    lines = ffmpeg(["-help", "long"]).split("\n")
    ginds = [
        (i + 1, l[:-1].lower())
        for i, l in enumerate(lines)
        if len(l) and l[0] not in "- \t" and l[-1] == ":"
    ]
    ginds.append((len(lines) + 1, None))

    def parse_line(s):
        m = re.match(r"\s*-(.+?) ([^ ]+?)? {2,}(.*)$", s)
        return (m[1], m[2], m[3]) if m else None

    raw_opts = (
        (
            l,
            {
                o[0]: o[1:]
                for o in (parse_line(s) for s in lines[i0 : i1 - 1])
                if o is not None
            },
        )
        for (i0, l), (i1, _) in zip(ginds[:-1], ginds[1:])
    )

    opts = {
        "video": {},
        "audio": {},
        "subtitle": {},
        "general": {},
        "global": {"overwrite": ("bool", "[ffmpegio] combining -y/-n options")},
    }
    for gname, gopts in raw_opts:
        if "video" in gname:
            opts["video"].update(gopts)
        elif "audio" in gname:
            opts["audio"].update(gopts)
        elif "subtitle" in gname:
            opts["subtitle"].update(gopts)
        elif "per-file" in gname:
            opts["general"].update(gopts)
        else:
            opts["global"].update(gopts)

    return opts


def options(
    type: (
        Literal["video", "audio", "subtitle", "data", "general", "global"] | None
    ) = None,
    name_only: bool = False,
    return_desc: bool = False,
) -> (
    dict[
        Literal["video", "audio", "subtitle", "data", "general", "global"],
        str,
    ]
    | dict[str, str | tuple[str, str]]
):
    """get FFmpeg command options

    :param type: specify option type to return, defaults to :code:`None` 
    :param name_only: True to only return option names, defaults to False
    :param return_desc: True to also return option description, defaults to False
    :return: option mapping depending on input arguments

    The FFmpeg options are retrieved by running :code:`ffmpeg -help long`. Its output
    is parsed then picked as specified by the arguments.
    """

    # parse all the options once (cached)
    opts = _parse_options()

    if type == "per-file":
        opts = {
            "per-file": {
                k: v for t, o in opts.items() if t != "global" for k, v in o.items()
            }
        }

    return (
        ({t: tuple(o) for t, o in opts.items()} if type is None else tuple(opts[type]))
        if name_only
        else (
            (
                opts
                if return_desc
                else {t: {k: v[0] for k, v in o.items()} for t, o in opts.items()}
            )
            if type is None
            else (
                opts[type] if return_desc else {k: v[0] for k, v in opts[type].items()}
            )
        )
    )


class FilterSummary(NamedTuple):
    """Summary tuple of an FFMpeg filter"""

    description: str
    """Description"""

    input: Literal["audio", "video", "dynamic", "none"]
    """Media type of input pads. 
    
    * :code:`"audio"` - audio streams 
    * :code:`"video"` - video streams
    * :code:`"dynamic"` - variable-length inputs
    * :code:`"none"` - no input pad"""

    num_inputs: int | None
    """number of input pads, :code:`None` if variable."""

    output: Literal["audio", "video", "dynamic", "none"]
    """Media type of output pads. 
    
    * :code:`"audio"` - audio streams 
    * :code:`"video"` - video streams
    * :code:`"dynamic"` - variable-length inputs
    * :code:`"none"` - no output pad"""

    num_outputs: int | None
    """number of output pads, :code:`None` if variable."""

    timeline_support: bool
    """:code:`True` if the filter supports `timeline editing <https://ffmpeg.org/ffmpeg-filters.html#Timeline-editing>`_"""

    slice_threading: bool
    """:code:`True` if the filter supports per-slice multi-threading"""

    command_support: bool
    """:code:`True` if the filter supports `runtime commands <https://ffmpeg.org/ffmpeg-filters.html#Changing-options-at-runtime-with-a-command>`_"""


@cache
def _parse_filters() -> dict[str, FilterSummary]:

    stdout = _("filters")
    types = {"A": "audio", "V": "video", "N": "dynamic", "|": "none"}

    data = {}
    for match in _filterRegexp.finditer(stdout):
        intype = types[match[5][0]]
        outtype = types[match[6][0]]
        data[match[4]] = FilterSummary(
            description=match[7],
            input=intype,
            num_inputs=(
                0
                if intype == "none"
                else len(match[5])
                if intype != "dynamic"
                else None
            ),
            output=outtype,
            num_outputs=(
                0
                if outtype == "none"
                else len(match[6])
                if outtype != "dynamic"
                else None
            ),
            timeline_support=match[1] == "T",
            slice_threading=match[2] == "S",
            command_support=match[3] == "C",
        )

    return data


def filters(
    io_type: Literal["audio", "video", "dynamic"] | None = None,
) -> dict[str, FilterSummary]:
    """get FFmpeg filters

    :param io_type: specify input or output stream type, defaults to :code:`None` 
    :return: dict of the summaries of the filters keyed by filter names

    Each key of the returned dict is a name of a filter and its value is a
    FilterSummary namedtuple with the following items:

    ================  ========  ===============================================
    Key               type      description
    ================  ========  ===============================================
    description       str       Short description of the filter
    input             str       Input stream type: 'audio'|'video'|'dynamic'
    num_inputs        int|None  Number of inputs or None if 'dynamic'
    output            str       Output stream type: 'audio'|'video'|'dynamic'
    num_outputs       int|None  Number of outputs or None if 'dynamic'
    timeline_support  bool      True if supports timeline editing
    slice_threading   bool      True if supports threading
    command_support   bool      True if supports command input from stdin
    ================  ========  ===============================================
    """

    data = _parse_filters()

    if io_type is not None:
        data = {
            k: v for k, v in data.items() if v.input == io_type or v.output == io_type
        }

    return data


class CodecSummaryDict(TypedDict):
    """Returned by :py:func:`codecs()`"""

    type: Literal["audio", "video", "subtitle"]
    """Stream media type"""
    description: str
    """Short description of the codec"""
    can_decode: bool
    """:code:`True` if FFmpeg can decode"""
    decoders: list(str)
    """List of compatible decoders"""
    can_encode: bool
    """:code:`True` if FFmpeg can encode"""
    encoders: list(str)
    """List of compatible encoders"""
    intra_frame_only: bool
    """:code:`True` if codec only uses intra-frame coding"""
    is_lossy: bool
    """:code:`True` if codec can do lossy compression"""
    is_lossless: bool
    """:code:`True` if codec can do lossless compression"""


@cache
def _parse_codecs() -> CodecSummaryDict:
    """get FFmpeg codecs

    :param type: Specify to list only decoder or encoder, defaults to :code:`None` 
    :param stream_type: Specify to stream type, defaults to :code:`None` 
    :return: summary of FFmpeg codecs

    Each key of the returned dict is a name of a codec and its value is
    """
    stdout = _("codecs")

    data = {}
    for match in _ffCodecRegexp.finditer(stdout):
        stype = {"V": "video", "A": "audio", "S": "subtitle"}[match[3]]

        desc = match[8]
        encoders = _ffEncodersRegexp.match(desc)
        if encoders:
            desc = desc.slice(0, encoders.index) + desc.slice(
                encoders.index + encoders[0].length
            )
        encoders = encoders[1].trim().split(" ") if encoders else None

        decoders = _ffDecodersRegexp.match(desc)
        if decoders:
            desc = desc.slice(0, decoders.index) + desc.slice(
                decoders.index + decoders[0].length
            )
        decoders = decoders[1].trim().split(" ") if decoders else None

        data[match[7]] = {
            "type": stype,
            "description": desc,
            "can_decode": match[1] == "D",
            "decoders": decoders,
            "can_encode": match[2] == "E",
            "encoders": encoders,
            "intra_frame_only": match[4] == "I",
            "is_lossy": match[5] == "L",
            "is_lossless": match[6] == "S",
        }
        if not encoders:
            del data[match[7]]["encoders"]
        if not decoders:
            del data[match[7]]["decoders"]

    return data


def codecs(
    codec_type: Literal["decoder", "encoder"] | None = None,
    stream_type: Literal["audio", "video", "subtitle"] | None = None,
) -> dict[str, CodecSummaryDict]:
    """get summary information of FFmpeg codecs

    :param codec_type: Specify to list only decoder or encoder, defaults to :code:`None` 
    :param stream_type: Specify to stream type, defaults to :code:`None` 
    :return: summary of FFmpeg codecs, keyed by codec name
    """
    data = _parse_codecs()

    # return all if no argument specified
    if codec_type is None and stream_type is None:
        return data

    decoder = codec_type is not None and codec_type == "decoder"
    encoder = codec_type is not None and codec_type == "encoder"
    stype = stream_type is not None

    def pick(entry):
        return (
            (decoder and entry["can_decode"]) or (encoder and entry["can_encode"])
        ) and (stype and stream_type == entry["type"])

    return {k: v for k, v in data.items() if pick(v)}


class EncoderSummaryDict(TypedDict):
    """Returned by :py:func:`encoders()`"""

    type: Literal["audio", "video", "subtitle"]
    """Stream media type"""
    description: str
    """Short description of the coder"""
    frame_mt: bool
    """:code:`True` if employs frame-level multithreading"""
    slice_mt: bool
    """:code:`True` if employs slice-level multithreading"""
    experimental: bool
    """:code:`True` if experimental encoder"""
    draw_horiz_band: bool
    """:code:`True` if supports draw_horiz_band"""
    directRendering: bool
    """:code:`True` if supports direct encoding method 1"""


def encoders(
    stream_type: Literal["audio", "video", "subtitle"] | None = None,
) -> dict[str, EncoderSummaryDict]:
    """get summary of FFmpeg encoders

    :param stream_type: specify stream type, defaults to :code:`None` 
    :return: dict of encoder information, keyed by the names of
        encoders and values :py:class:`EncoderSummaryDict` objects.
    """

    data = _parse_coders("encoders")
    if stream_type is not None:
        data = {k: v for k, v in data.items() if v["type"] == stream_type}
    return data


class DecoderSummaryDict(TypedDict):
    """Returned by :py:func:`decoders()`"""

    type: Literal["audio", "video", "subtitle"]
    """Stream type"""
    description: str
    """Short description of the coder"""
    frame_mt: bool
    """:code:`True` if employs frame-level multithreading"""
    slice_mt: bool
    """:code:`True` if employs slice-level multithreading"""
    experimental: bool
    """:code:`True` if experimental encoder"""
    draw_horiz_band: bool
    """:code:`True` if supports draw_horiz_band"""
    directRendering: bool
    """:code:`True` if supports direct encoding method 1"""


def decoders(
    stream_type: Literal["audio", "video", "subtitle"] | None = None,
) -> dict[str, DecoderSummaryDict]:
    """get summary of FFmpeg decoders

    :param stream_type: specify stream type, defaults to :code:`None` 
    :return: dict of decoder information, keyed by the names of
        decoders and values :py:class:`DecoderSummaryDict` objects.
    """

    data = _parse_coders("decoders")
    if stream_type is not None:
        data = {k: v for k, v in data.items() if v["type"] == stream_type}
    return data


@cache
def _parse_coders(codec_type):
    # reversed fftools/comdutils.c show_encoders()

    stdout = _(codec_type)

    data = {}
    for match in _coderRegexp.finditer(stdout):
        stype = {"V": "video", "A": "audio", "S": "subtitle"}[match[1]]
        data[match[7]] = {
            "type": stype,
            "description": match[8],
            "frame_mt": match[2] == "F",
            "slice_mt": match[3] == "S",
            "experimental": match[4] == "X",
            "draw_horiz_band": match[5] == "B",
            "directRendering": match[6] == "D",
        }

    return data


#   / **
#    * reversed fftools/comdutils.c show_formats()
#    * /


class FormatSummaryDict(TypedDict):
    """Returned by :py:func:`formats()`, :py:func:`devices()`, :py:func:`muxers()`, and :py:func:`demuxers()`"""

    description: str
    """Short description of the format/device"""
    can_demux: bool
    """:code:`True` if supports inputs of this format/device"""
    can_mux: bool
    """:code:`True` if support outputs of this format/device"""
    is_device: bool
    """:code:`True` if format is a device"""


def formats(
    return_names_only: bool = False,
) -> dict[str, FormatSummaryDict] | list[str]:
    """get FFmpeg formats

    :param return_names_only: True to return a list of format names, defaults to False
        to return a dict of formats with their summary information.
    :return: available formats

        * if :code:`return_names_only=False` a dict of :py:class:`FormatSummaryDict` keyed
          by the format names.
        * if :code:`return_names_only=True` a list of format names.

    """

    data = _parse_formats()
    return list(data) if return_names_only else data


def devices(
    source_or_sink: Literal["source", "sink"] | None = None,
    return_names_only: bool = False,
) -> dict[str, FormatSummaryDict] | list[str]:
    """get FFmpeg devices

    :param source_or_sink: specify source or sink type, defaults to :code:`None`  to return both
    :param return_names_only: True to return a list of device names, defaults to False
        to return a dict of devices with their summary information.
    :return: available devices

        * if :code:`return_names_only=False` a dict of :py:class:`FormatSummaryDict` keyed
          by the device names.
        * if :code:`return_names_only=True` a list of device names.
    """
    data = _parse_formats()

    checker = (
        (lambda p: p["is_device"] and p["can_demux"])
        if source_or_sink == "source"
        else (
            (lambda p: p["is_device"] and p["can_mux"])
            if source_or_sink == "sink"
            else (lambda p: p["is_device"])
        )
    )

    keep = [checker(props) for props in data.values()]

    if return_names_only:
        return [name for name, tf in zip(data, keep) if tf]

    return {name: props for (name, props), tf in zip(data.items(), keep) if tf}


def muxers(
    include_devices: bool = False, return_names_only: bool = False
) -> list[str] | dict[str, FormatSummaryDict]:
    """get FFmpeg muxers

    :param include_devices: True to include input devices, defaults to False
    :param return_names_only: True to return only the list of muxers, defaults to False
    :return: a dict of muxers and their basic properties or a list of muxers if
             :code:`return_names_only==True`


    Each key of the returned dict is a name of a muxer and its value is a dict
    with the following items:

    ================  ====  ===============================================
    Key               type  description
    ================  ====  ===============================================
    description       str   Short description of the muxer
    ================  ====  ===============================================
    """
    return _filtered_formats("can_mux", include_devices, return_names_only)


def demuxers(
    include_devices: bool = False, return_names_only: bool = False
) -> list[str] | dict[str, FormatSummaryDict]:
    """get FFmpeg demuxers

    :param include_devices: True to include input devices, defaults to False
    :param return_names_only: True to return only the list of demuxers, defaults to False
    :return: a dict of demuxers and their basic properties or a list of demuxers if
             :code:`return_names_only==True`


    Each key of the returned dict is a name of a demuxer and its value is a dict
    with the following items:

    ================  ====  ===============================================
    Key               type  description
    ================  ====  ===============================================
    description       str   Short description of the demuxer
    ================  ====  ===============================================
    """

    return _filtered_formats("can_demux", include_devices, return_names_only)


def _filtered_formats(
    can_do: Literal["can_demux", "can_mux"],
    include_devices: bool = False,
    return_names_only: bool = False,
):

    data = _parse_formats()

    checker = (
        (lambda p: p[can_do])
        if include_devices
        else (lambda p: p[can_do] and not p["is_device"])
    )

    keep = [checker(props) for props in data.values()]

    if return_names_only:
        return [name for name, tf in zip(data, keep) if tf]

    return {name: props for (name, props), tf in zip(data.items(), keep) if tf}


@cache
def _parse_formats() -> dict[str, dict]:
    stdout = _("formats")

    data = {}
    for match in _formatRegexp.finditer(stdout):
        for format in match[4].split(","):
            data[format] = {"description": match[4]}
            data[format]["can_demux"] = match[1] == "D"
            data[format]["can_mux"] = match[2] == "E"
            data[format]["is_device"] = match[3] == "d"

    return data


#   // reversed fftools/comdutils.c show_bsfs()


@cache
def bsfilters() -> list[str]:
    """get list of FFmpeg bitstream filters

    :return: list of bistream filters
    """
    stdout = _("bsfs")
    m = re.match(r"\s*Bitstream filters:\s+([\s\S]+)\s*", stdout)
    return re.split(r"\s*\n\s*", m[1].strip())


#   // reversed fftools/comdutils.c show_protocols()


@cache
def protocols() -> dict[str, dict]:
    """get list of supported protocols

    :return: list of protocols

    Returned dict has 'input' and 'output' keys and each contains a list of
    supported protocol names.

    """
    stdout = _("protocols")
    match = re.search(r"Input:\s+([\s\S]+)Output:\s+([\s\S]+)", stdout)
    return dict(
        input=re.split(r"\s*\n\s*", match[1]), output=re.split(r"\s*\n\s*", match[1])
    )


#   // according to fftools/comdutils.c show_pix_fmts()


class PixFmtInfoDict(TypedDict):
    nb_components: int
    """Number of color components"""
    bits_per_pixel: int
    """Number of bits per pixel"""
    input: bool
    """:code:`True` if can be used as an input option"""
    output: bool
    """:code:`True` if can be used as an output option"""
    hw_accel: bool
    """:code:`True` if supported by hardware accelerators"""
    paletted: bool
    """:code:`True` if uses paletted colors"""
    bitstream: bool
    """:code:`True` if can be used with bistreams"""


@cache
def pix_fmts() -> dict[str, PixFmtInfoDict]:
    """get supported pixel formats

    :return: list of supported pixel formats

    Each key of the returned dict is a name of a pix_fmt and its value is a dict
    with the following items:

    ==============  ====  ===============================================
    Key             type  description
    ==============  ====  ===============================================
    ==============  ====  ===============================================
    """
    stdout = _("pix_fmts")

    data = {
        match[6]: dict(
            nb_components=int(match[7]),
            bits_per_pixel=int(match[8]),
            input=match[1] == "I",
            output=match[2] == "O",
            hw_accel=match[3] == "H",
            paletted=match[4] == "P",
            bitstream=match[5] == "B",
        )
        for match in re.finditer(
            r"([I.])([O.])([H.])([P.])([B.])\s+(\S+)\s+(\d+)\s+(\d+)", stdout
        )
    }

    return data


@cache
def sample_fmts() -> dict[str, dict]:
    """get supported audio sample formats

    :return: list of supported audio sample formats

    Each key of the returned dict is a name of a sample_fmt and its value
    is the number of bits per sample.
    """

    #   // according to fftools/comdutils.c show_sample_fmts()
    stdout = _("sample_fmts")
    return {match[1]: int(match[2]) for match in re.finditer(r"(\S+)\s+(\d+)", stdout)}


@cache
def layouts() -> dict[Literal["channels", "layouts"], dict[str, str]]:
    """get supported audio channel layouts

    :return: list of supported audio channel layouts

    Returned dict has two keys "channels" and "layouts". The value of "channels"
    is a dict of possible channel names as keys and their descriptions as values.
    The value of "layouts" is also a dict, which keys specifies the names and
    their value strs indicate the combinations of channels (their names are
    "+"ed).
    """

    #   // according to fftools/comdutils.c show_layouts()
    stdout = _("layouts")

    match = re.match(
        r"\s*Individual channels:\s+NAME\s+DESCRIPTION\s+(\S[\s\S]+)Standard channel layouts:\s+NAME\s+DECOMPOSITION\s+(\S[\s\S]+)",
        stdout,
    )
    return dict(
        channels={
            m[1]: m[2] for m in re.finditer(r"(\S+)\s+\s([\s\S]+?)\s*\n", match[1])
        },
        layouts={
            m[1]: m[2] for m in re.finditer(r"(\S+)\s+(\S[\s\S]+?)\s*\n", match[2])
        },
    )


@cache
def colors() -> dict[str, str]:
    """get recognized color names

    :return: list of color names

    The keys of the returned dict are the name of the colors and their values
    are the RGB hex strs.
    """

    #   // according to fftools/comdutils.c show_colors()
    stdout = _("colors")

    return {
        match[1]: match[2]
        for match in re.finditer(r"(\S+)\s+(\#[0-9a-f]{6})\s*?\n", stdout)
    }


class DemuxerInfoDict(TypedDict):
    """Returned by :py:func:`demuxer_info()`"""

    names: list[str]
    """List of compatible short names"""
    long_name: str
    """Common long name"""
    extensions: list[str]
    """List of associated common extensions (w/out :code:`'.'`)"""
    options: str
    """Unparsed string, listing supported options (TODO)"""


@cache
def demuxer_info(name: str) -> DemuxerInfoDict:
    """get detailed info of a media demuxer

    :return: demuxer features

    """

    #   // according to fftools/comdutils.c show_help_demuxer()
    stdout = __("demuxer", name)
    if stdout.startswith("Unknown"):
        raise FFmpegError(stdout)

    m = re.match(
        r"Demuxer (\S+) \[([^\]]+)\]:\s*?\n(?:    Common extensions: ([^.]+)\.\s*\n)?([\s\S]*)",
        stdout,
    )

    return dict(
        names=m[1].split(","),
        long_name=m[2],
        extensions=m[3].split(",") if m[3] else [],
        options=m[4],
    )


class MuxerInfoDict(TypedDict):
    """Returned by :py:func:`muxer_info()`"""

    names: list[str]
    """List of compatible short names"""
    long_name: str
    """Common long name"""
    extensions: list[str]
    """List of associated common extensions (w/out :code:'.')"""
    mime_types: list[str]
    """List of associated MIME types"""
    video_codecs: list[str]
    """List of supported video codecs"""
    audio_codecs: list[str]
    """List of supported audio codecs"""
    subtitle_codecs: list[str]
    """List of supported subtitle codecs"""
    options: str
    """Unparsed string, listing supported options (TODO)"""


@cache
def muxer_info(name: str) -> MuxerInfoDict:
    """get detailed info of a media muxer

    :return: muxer features

    """

    #   // according to fftools/comdutils.c show_help_muxer()

    stdout = __("muxer", name)
    if stdout.startswith("Unknown format"):
        raise FFmpegError(stdout)

    m = re.match(
        r"Muxer (\S+) \[([^\]]+)\]:\s*?\n(?:    Common extensions: ([^.]+)\.\s*?\n)?(?:    Mime type: ([^.]+)\.\s*?\n)?(?:    Default video codec: ([^.]+)\.\s*?\n)?(?:    Default audio codec: ([^.]+)\.\s*?\n)?(?:    Default subtitle codec: ([^.]+).\s*?\n)?([\s\S]*)",
        stdout,
    )

    return {
        "names": m[1].split(","),
        "long_name": m[2],
        "extensions": m[3].split(",") if m[3] else [],
        "mime_types": m[4].split(",") if m[4] else [],
        "video_codecs": m[5].split(",") if m[5] else [],
        "audio_codecs": m[6].split(",") if m[6] else [],
        "subtitle_codecs": m[7].split(",") if m[7] else [],
        "options": m[8],
    }


class EncoderInfoDict(TypedDict):
    """Returned by :py:func:`encoder_info()`"""

    name: list[str]
    """Short names"""
    long_name: str
    """Long name"""
    capabilities: list[str]
    """List of supported capabilities"""
    threading: list[str]
    """List of threading capabilities"""
    supported_hwdevices: list[str]
    """List of supported hardware accelerators"""
    supported_framerates: list[Fraction]
    """List of supported video frame rates"""
    supported_pix_fmts: list[str]
    """List of supported video pixel formats"""
    supported_sample_rates: list[int]
    """List of supported audio sample rates"""
    supported_sample_fmts: list[str]
    """List of supported audio sample formats"""
    supported_layouts: list[str]
    """List of supported audio channel layouts"""
    options: str
    """Unparsed string, listing supported options"""


@cache
def encoder_info(name: str) -> EncoderInfoDict:
    """get detailed info of an encoder

    :param name: encoder name
    :return: encoder features
    """
    return _parse_codec_info(name, True)


class DecoderInfoDict(TypedDict):
    """Returned by :py:func:`decoder_info()`"""

    name: list[str]
    """Short names"""
    long_name: str
    """Long name"""
    capabilities: list[str]
    """List of supported capabilities"""
    threading: list[str]
    """List of threading capabilities"""
    supported_hwdevices: list[str]
    """List of supported hardware accelerators"""
    supported_framerates: list[Fraction]
    """List of supported video frame rates"""
    supported_pix_fmts: list[str]
    """List of supported video pixel formats"""
    supported_sample_rates: list[int]
    """List of supported audio sample rates"""
    supported_sample_fmts: list[str]
    """List of supported audio sample formats"""
    supported_layouts: list[str]
    """List of supported audio channel layouts"""
    options: str
    """Unparsed string, listing supported options (TODO)"""


@cache
def decoder_info(name: str) -> DecoderInfoDict:
    """get detailed info of a decoder

    :param name: decoder name
    :return: decoder features
    """
    return _parse_codec_info(name, False)


def _parse_codec_info(name: str, encoder: bool) -> dict:
    #   // according to fftools/comdutils.c show_help_codec()
    stdout = __("encoder" if encoder else "decoder", name)
    if "is not recognized" in stdout:
        raise FFmpegError(stdout)

    type = "Encoder" if encoder else "Decoder"
    m = re.match(
        type
        + r" (\S+) \[([^\]]*)\]:\s*?\n"
        + r"    General capabilities: ([^\r\n]*?)\s*?\n"
        + r"(?:    Threading capabilities: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported hardware devices: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported framerates: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported pixel formats: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported sample rates: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported sample formats: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported channel layouts: ([^\r\n]*?)\s*?\n)?"
        + r"([\s\S]*)",
        stdout,
    )

    if m is None:
        raise FFmpegError(stdout)

    def resolveFs(s):
        m = re.match(r"(\d+)\/(\d+)", s)
        return fractions.Fraction(int(m[1]), int(m[2]))

    _re_layouts = re.compile(
        re.sub(r"([().])", r"\\\1", "|".join(layouts()["layouts"]))
        + r"|\d+ channels \(.+?\)"
    )

    return {
        "name": m[1],
        "long_name": m[2],
        "capabilities": m[3].split(" ") if m[3] and m[3] != "none" else [],
        "threading": m[4].split(" and ") if m[4] and m[4] != "none" else [],
        "supported_hwdevices": m[5].split(" ") if m[5] else [],
        "supported_framerates": [resolveFs(s) for s in m[6].split(" ")] if m[6] else [],
        "supported_pix_fmts": m[7].split(" ") if m[7] else [],
        "supported_sample_rates": [int(v) for v in m[8].split(" ")] if m[8] else [],
        "supported_sample_fmts": m[9].split(" ") if m[9] else [],
        "supported_layouts": _re_layouts.findall(m[10]) if m[10] else [],
        "options": m[11],
    }


def _get_filter_pad_info(line: str) -> list[dict[str, str]] | None:
    if line.startswith("        dynamic"):
        return None
    elif line.startswith("        none"):
        return []

    matches = re.finditer(r"       #\d+: (\S+)(?= \() \((\S+)\)\s*?(?:\n|$)", line)
    if not matches:
        raise Exception("Failed to parse filter port info: %s" % line)
    return [{"name": m[1], "type": m[2]} for m in matches]


Tin = TypeVar("Tin")
Tout = TypeVar("Tout")


def _conv_func(out_type: Callable[[Tin], Tout], s: Tin) -> Tout | Tin:
    try:
        return out_type(s)
    except:
        return s


def _get_filter_option_constant(
    line: str, is_flag: bool = False
) -> tuple[str, str] | tuple[tuple[str, int], str]:
    # from libavutil/opts.c opt_list() with flags AV_OPT_FLAG_FILTERING_PARAM and AV_OPT_TYPE_CONST

    m = re.match(
        r"     (.+?)[.E][.D][.F][.V][.A][.S][.X][.R][.B][.T][.P](?: (.+))?",
        line,
    )
    desc = m[2] or ""

    if is_flag:
        return m[1].strip(), desc
    else:
        name, intval = m[1].rsplit(maxsplit=1)
        return (name, int(intval)), desc


class FilterOption(NamedTuple):
    """FFmpeg filter option tuple

    This tuple is used for the elements of :py:attr:`FilterInfo.options` and :py:attr:`FilterInfo.extra_options`"""

    name: str
    """option name"""

    aliases: list[str]
    """option name aliases"""

    type: Literal[
        "string",
        "boolean",
        "int",
        "int64",
        "uint64",
        "float",
        "double",
        "rational",
        "flags",
    ]
    """option data type"""

    multiple: bool
    """:code:`True` if multiple value assignable via :code:`|`-separated list"""

    help: str
    """option description"""

    ranges: tuple[int | float | Fraction, int | float | Fraction] | None
    """valid range of the option value"""

    constants: dict[str | int, str] | None
    """dict of acceptable values. Keys are allowed option values and dict values
    are descriptions of the constants"""

    default: str | bool | int | float | Fraction | None
    """default option value"""

    video: bool
    """:code:`True` if affecting video stream
    """
    audio: bool
    """:code:`True` if affecting audio stream
    """
    runtime: bool
    """:code:`True` if modifiable during runtime
    """


def _get_filter_option(block: str, name: str) -> FilterOption:
    # from libavutil/opts.c opt_list() with flags AV_OPT_FLAG_FILTERING_PARAM

    lines = block.splitlines()

    # first line is the main option definition
    m0 = re.match(
        r"  (?: |-)([^ \n]+?) +(.+?)[.E][.D][.F]([.V])([.A])[.S][.X][.R][.B]([.T])[.P]",
        lines[0],
    )
    if not m0:
        raise FFmpegioError(
            f"Failed to parse option line ({lines[0]}) of {name} filter (maybe unsupported FFmpeg version)"
        )
    name, otype, *flags = m0.groups()

    multiple = otype.startswith("[")  # multiple value assignable via |-separated list
    otype = (otype[1:-1] if multiple else otype).strip()[1:-1]

    m1 = re.search(r"( \(from \S+? to \S+?\))*(?: \(default (.+)\))?$", lines[0])
    ranges_str, default_val = m1.groups()

    help = lines[0][m0.end() + 1 : m1.start()]

    if default_val:
        if otype == "string":
            # remove quotes
            default_val = default_val[1:-1]
        elif otype == "boolean":
            default_val = {"true": True, "false": False}.get(default_val, default_val)

    conv = (
        partial(_conv_func, int)
        if otype in ("int", "int64", "uint64")
        else (
            partial(_conv_func, float)
            if otype in ("float", "double")
            else partial(_conv_func, Fraction)
            if otype == "rational"
            else (lambda s: s)
        )
    )

    ranges = (
        None
        if ranges_str is None
        else [
            (conv(m[1]), conv(m[2]))
            for m in re.finditer(r"\(from (\S+?) to (\S+?)\)", ranges_str)
        ]
    )

    constants = [
        _get_filter_option_constant(l, otype == "flags") for l in lines[1:] if l
    ]

    if not len(constants):
        cdict = None
    elif otype == "int":
        # add int values as constant entries
        cdict = {}
        for (k, kint), v in constants:
            cdict[k] = v
            cdict[kint] = v
    else:
        cdict = dict(constants)

    return FilterOption(
        name,
        [],
        otype,
        multiple,
        help,
        ranges,
        cdict,
        conv(default_val),
        *(fl != "." for fl in flags),
    )


def _get_filter_options(block: str) -> tuple[str, list[FilterOption]]:
    m = re.match(r"(.+)? AVOptions:\n", block)
    assert m is not None
    name = m[1]
    blocks = re.split(r"\n(?!     |\n|$)", block[m.end() :])
    opts = [_get_filter_option(line, name) for line in blocks if line and line != "\n"]

    # combines aliases
    def is_alias(i, o):
        other = opts[i]
        return other.type == o.type and other.help == o.help

    n = len(opts)
    i = 0
    alias_of = [-1] * n
    for j, o in enumerate(opts[1:]):
        if is_alias(i, o):
            alias_of[j + 1] = i
        else:
            i = j + 1

    im = [*[i for i, j in enumerate(alias_of) if j < 0], n]

    for i0, i1 in zip(im[:-1], im[1:]):
        if i1 - i0 > 1:
            v = list(opts[i0])
            v[1] = [o.name for o in opts[i0 + 1 : i1]]
            opts[i0] = FilterOption(*v)

    opts = [o for o, isa in zip(opts, alias_of) if isa < 0]

    return name, opts


class FilterInfoPadDict(TypedDict):
    """Input/output pad definition dict"""

    name: str
    "Pad name"
    type: Literal["audio", "video"]
    "Media type"


class FilterInfo(NamedTuple):
    """Return type of :py:func:`filter_info()`"""

    name: str
    """Filter name"""
    description: str
    """Description"""
    threading: list[str]
    """list of threading capabilities"""
    inputs: list[FilterInfoPadDict] | Literal["dynamic"]
    """list of input pads"""
    outputs: list[FilterInfoPadDict] | Literal["dynamic"]
    """list of output pads"""
    options: list[FilterOption]
    """list of filter options"""
    extra_options: list[FilterOption]
    """list of additional filter option, usually shared with other filters"""
    timeline_support: bool
    """:code:`True` if `timeline editing <https://ffmpeg.org/ffmpeg-filters.html#Timeline-editing>`_ is supported"""


@cache
def filter_info(name: str) -> FilterInfo:
    """get detailed info of a filter

    :param name: filter name
    :return: filter features

    """

    #   // according to fftools/comdutils.c show_help_filter()
    stdout = __("filter", name)

    if stdout.startswith("Unknown"):
        raise FFmpegError(stdout)

    blocks = re.split(r"\n(?! |\n|$)", stdout)
    if blocks[-1].startswith("Exiting with exit code"):
        blocks = blocks[:-1]

    m = re.match(
        r"Filter (\S+)\s*?\n"
        r"(?:  (.+?)\s*?\n)?"
        r"(?:    (slice threading supported)\s*?\n)?"
        r"    Inputs:\n"
        r"([\s\S]*)"
        r"    Outputs:\n"
        r"([\s\S]*)",
        blocks[0],
    )

    if m is None:
        raise FFmpegError(blocks[0])

    name = m[1]
    desc = m[2]
    threading = ["slice"] if m[3] else []
    inputs = _get_filter_pad_info(m[4])
    outputs = _get_filter_pad_info(m[5])
    timeline = (
        blocks[-1].rstrip()
        == "This filter has support for timeline through the 'enable' option."
    )

    extra_options = dict(
        (_get_filter_options(b) for b in (blocks[1:-1] if timeline else blocks[1:]))
    )

    options = extra_options.pop(name, None) if len(extra_options) else []
    if options is None:  # options are shared among multiple filters
        # fix filter name/AVOptions block name inconsistency
        avopt_name = {
            "vsrc_amf": "amf_capture"  # v8.1
        }.get(name, name)

        def check_o_name(o_name, name):
            if o_name.startswith("cuda"):
                return f"{o_name[4:]}_cuda"

            m = re.search(r"\(([^|]+)\)", o_name)
            if m:
                # add ? to make parenthetical field optional
                i = m.end(1) + 1
                o_name = f"{o_name[:i]}?{o_name[i:]}"
            else:
                # shared filters separated by '/' -> use '|' for regex
                o_name = o_name.replace("/", "|")
            return re.match(o_name, name)

        try:
            opt_name = next(
                (
                    o_name
                    for o_name in extra_options.keys()
                    if check_o_name(o_name, avopt_name)
                ),
            )
        except StopIteration as e:
            raise FFmpegioError(
                f"filter_info({name}): none of the AVOption sets appears to be the main option set:\n   {[k for k in extra_options]}"
            ) from e

        options = extra_options.pop(opt_name)

    return FilterInfo(
        name,
        desc,
        threading,
        inputs,
        outputs,
        options,
        extra_options,
        timeline,
    )


class BSFInfo(NamedTuple):
    """Return type of :py:func:`bsfilter_info()`"""

    name: str
    """filter name"""
    supported_codecs: list[str]
    """list of codecs supporting this filter"""
    options: str
    """unparsed string, listing supported options (TODO)"""


@cache
def bsfilter_info(name: str) -> BSFInfo:
    """get detailed info of a bitstream filter

    :return: bistream filter features

    """

    #   // according to fftools/comdutils.c show_help_bsf()
    stdout = __("bsf", name)

    m = re.match(
        r"Bit stream filter (\S+)\s*?\n"
        r"(?:    Supported codecs: ([^\r\n]+?)\s*?\n)?"
        r"([\s\S]*)",
        stdout,
    )

    if stdout.startswith("Unknown"):
        raise FFmpegError(stdout)

    return BSFInfo(
        m[1],  # "name"
        m[2].split(" ") if m[2] else [],  # "supported_codecs"
        m[3],  # "options"
    )


@cache
def dispositions() -> list[str]:
    """get a list of supported stream dispositions

    The list is obtained by parsing the output of::

        ffmpeg -dispositions

    """
    stdout = _("dispositions")

    return stdout.splitlines(keepends=False)


video_size_presets: dict[LiteralString, tuple[int, int]] = {
    "ntsc": (720, 480),
    "pal": (720, 576),
    "qntsc": (352, 240),
    "qpal": (352, 288),
    "sntsc": (640, 480),
    "spal": (768, 576),
    "film": (352, 240),
    "ntsc-film": (352, 240),
    "sqcif": (128, 96),
    "qcif": (176, 144),
    "cif": (352, 288),
    "4cif": (704, 576),
    "16cif": (1408, 1152),
    "qqvga": (160, 120),
    "qvga": (320, 240),
    "vga": (640, 480),
    "svga": (800, 600),
    "xga": (1024, 768),
    "uxga": (1600, 1200),
    "qxga": (2048, 1536),
    "sxga": (1280, 1024),
    "qsxga": (2560, 2048),
    "hsxga": (5120, 4096),
    "wvga": (852, 480),
    "wxga": (1366, 768),
    "wsxga": (1600, 1024),
    "wuxga": (1920, 1200),
    "woxga": (2560, 1600),
    "wqsxga": (3200, 2048),
    "wquxga": (3840, 2400),
    "whsxga": (6400, 4096),
    "whuxga": (7680, 4800),
    "cga": (320, 200),
    "ega": (640, 350),
    "hd480": (852, 480),
    "hd720": (1280, 720),
    "hd1080": (1920, 1080),
    "2k": (2048, 1080),
    "2kflat": (1998, 1080),
    "2kscope": (2048, 858),
    "4k": (4096, 2160),
    "4kflat": (3996, 2160),
    "4kscope": (4096, 1716),
    "nhd": (640, 360),
    "hqvga": (240, 160),
    "wqvga": (400, 240),
    "fwqvga": (432, 240),
    "hvga": (480, 320),
    "qhd": (960, 540),
    "2kdci": (2048, 1080),
    "4kdci": (4096, 2160),
    "uhd2160": (3840, 2160),
    "uhd4320": (7680, 4320),
}
"""list of video size presets with their sizes"""

frame_rate_presets: dict[LiteralString, fractions.Fraction] = {
    "ntsc": fractions.Fraction(30000, 1001),
    "pal": fractions.Fraction(25, 1),
    "qntsc": fractions.Fraction(30000, 1001),
    "qpal": fractions.Fraction(25, 1),
    "sntsc": fractions.Fraction(30000, 1001),
    "spal": fractions.Fraction(25, 1),
    "film": fractions.Fraction(24, 1),
    "ntsc-film": fractions.Fraction(24000, 1001),
}
"""list of video frame rate presets with their rates"""
