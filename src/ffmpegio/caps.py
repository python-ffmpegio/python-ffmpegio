# TODO add function to guess media type given extension

from . import ffmpeg
import re, fractions

_ffCodecRegexp = re.compile(
    r"([D.])([E.])([VAS])([I.])([L.])([S.])\s+([^=\s][\S]*)\s+(.*)"
)  # g
_ffEncodersRegexp = re.compile(r"\s+\(encoders:([^\)]+)\)")
_ffDecodersRegexp = re.compile(r"\s+\(decoders:([^\)]+)\)")
_coderRegexp = re.compile(
    r"([VAS])([F.])([S.])([X.])([B.])([D.])\s+([^=\s]\S*)\s+(.*)"
)  # g
_formatRegexp = re.compile(r"([D ])([E ]) (\S+) +(.*)")  # g
_filterRegexp = re.compile(
    r"([T.])([S.])([C.])\s+(\S+)\s+(A+|V+|N|\|)->(A+|V+|N|\|)\s+(.*)"
)  # g

_cache = dict()


def _(cap):
    return (
        (None, _cache[cap])
        if ("cap" in _cache)
        else (ffmpeg.ffprobe([f"-{cap}"], stderr=None), None)
    )


def __(type, name):
    return (
        (None, _cache[type][name])
        if (type in _cache and name in _cache[type])
        else (ffmpeg.ffprobe(["--help", f"{type}={name}"], stderr=None), None)
    )


#   / **
#    * A callback passed to {@link FfmpegCommand  # availableFilters}.
#    *
#    * @callback FfmpegCommand~filterCallback
#    * @param {Function} spawnSyncUtf8 def to synchronously spawn FFmpeg
#    * @returns {Object} filter object with filter names as keys and the following
#    * properties for each filter:
#    * @returns {String} filters.description filter description
#    * @returns {String} filters.input input type, one of 'audio', 'video' and 'none'
#    * @returns {Boolean} filters.multipleInputs whether the filter supports multiple inputs
#    * @returns {String} filters.output output type, one of 'audio', 'video' and 'none'
#    * @returns {Boolean} filters.multipleOutputs whether the filter supports multiple outputs
#    * @returns {Exception | null} err error object or null if no error happened
#    * /

#   / **
#    * reversed fftools/comdutils.c show_filters()
#    *
#    * @method FfmpegCommand  # availableFilters
#    * @category Capabilities
#    * @aliases getAvailableFilters
#    *
#    * @param {FfmpegCommand~filterCallback} callback callback function
#    * /
def filters():
    stdout, data = _("filters")
    if data:
        return data

    types = {"A": "audio", "V": "video", "N": "dynamic", "|": "none"}

    data = {}
    for match in _filterRegexp.finditer(stdout):
        print(match[5])
        data[match[4]] = {
            "description": match[7],
            "input": types[match[5][0]],
            "multipleInputs": len(match[5]) > 1,
            "output": types[match[6][0]],
            "multipleOutputs": len(match[6]) > 1,
            "timelineSupport": match[1] == "T",
            "sliceThreading": match[2] == "S",
            "commandSupport": match[3] == "C",
        }

    _cache["filters"] = data
    return data


#   / **
#    * A callback passed to {@link FfmpegCommand  # availableCodecs}.
#    *
#    * @callback FfmpegCommand~codecCallback
#    * @param {Exception | null} err error object or null if no error happened
#    * @param {Object} codecs codec object with codec names as keys and the following
#    * properties for each codec(more properties may be available depending on the
#    * ffmpeg version used):
#    * @param {String} codecs.description codec description
#    * @param {Boolean} codecs.can_decode whether the codec is able to decode streams
#    * @param {Boolean} codecs.can_encode whether the codec is able to encode streams
#    * /

#   / **
#    * reversed fftools/comdutils.c show_codecs()
#    *
#    * @method FfmpegCommand  # availableCodecs
#    * @category Capabilities
#    * @aliases getAvailableCodecs
#    *
#    * @param {FfmpegCommand~codecCallback} callback callback function
#    * /


def codecs(type=None, stream_type=None):
    stdout, data = _("codecs")
    if data:
        return data

    must_decode = type is not None and type == "decoder"
    must_encode = type is not None and type == "encoder"

    data = {}
    for match in _ffCodecRegexp.finditer(stdout):

        if must_decode and match[1] != "D":
            continue
        if must_encode and match[2] != "E":
            continue

        stype = {"V": "video", "A": "audio", "S": "subtitle"}[match[3]]
        if stream_type and stype != stream_type:
            continue

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

    _cache["codecs"] = data
    return data


#   / **
#    * A callback passed to {@link FfmpegCommand  # availableEncoders}.
#    *
#    * @callback FfmpegCommand~encodersCallback
#    * @param {Exception | null} err error object or null if no error happened
#    * @param {Object} encoders encoders object with encoder names as keys and the following
#    * properties for each encoder:
#    * @param {String} encoders.description codec description
#    * @param {Boolean} encoders.type "audio", "video" or "subtitle"
#    * @param {Boolean} encoders.frame_mt whether the encoder is able to do frame-level multithreading
#    * @param {Boolean} encoders.slice_mt whether the encoder is able to do slice-level multithreading
#    * @param {Boolean} encoders.experimental whether the encoder is experimental
#    * @param {Boolean} encoders.draw_horiz_band whether the encoder supports draw_horiz_band
#    * @param {Boolean} encoders.directRendering whether the encoder supports direct encoding method 1
#    * /

#   / **
#    * reversed fftools/comdutils.c show_encoders()
#    *
#    * @method FfmpegCommand  # availableEncoders
#    * @category Capabilities
#    * @aliases getAvailableEncoders
#    *
#    * @param {FfmpegCommand~encodersCallback} callback callback function
#    * /


def coders(type, stream_type=None):
    stdout, data = _(type)
    if data:
        return data

    data = {}
    for match in _coderRegexp.finditer(stdout):
        stype = {"V": "video", "A": "audio", "S": "subtitle"}[match[1]]
        if stream_type and stream_type != stype:
            continue
        data[match[7]] = {
            "type": stype,
            "description": match[8],
            "frame_mt": match[2] == "F",
            "slice_mt": match[3] == "S",
            "experimental": match[4] == "X",
            "draw_horiz_band": match[5] == "B",
            "directRendering": match[6] == "D",
        }

    _cache[type] = data
    return data


#   / **
#    * A callback passed to {@link FfmpegCommand  # formats}.
#    *
#    * @callback FfmpegCommand~formatCallback
#    * @param {Exception | null} err error object or null if no error happened
#    * @param {Object} formats format object with format names as keys and the following
#    * properties for each format:
#    * @param {String} formats.description format description
#    * @param {Boolean} formats.can_demux whether the format is able to demux streams from an input file
#    * @param {Boolean} formats.can_mux whether the format is able to mux streams into an output file
#    * /

#   / **
#    * reversed fftools/comdutils.c show_formats()
#    *
#    * @method FfmpegCommand  # formats
#    * @category Capabilities
#    * /


def formats():
    return _getFormats("formats")


def devices():
    return _getFormats("devices")


def muxers():
    return _getFormats("muxers")


def demuxers():
    return _getFormats("demuxers")


def _getFormats(type):
    stdout, data = _(type)
    if data:
        return data

    doCan = type == "formats" or type == "devices"
    data = {}
    for match in _formatRegexp.finditer(stdout):
        for format in match[3].split(","):
            if not (format in data):
                data[format] = {"description": match[4]}
            if doCan:
                data[format]["can_demux"] = match[1] == "D"
                data[format]["can_mux"] = match[2] == "E"

    _cache[type] = data
    return data


#   // reversed fftools/comdutils.c show_bsfs()


def bsfilters():
    stdout, data = _("bsfs")
    if data:
        return data

    m = re.match(r"\s*Bitstream filters:\s+([\s\S]+)\s*", stdout)
    _cache["bsfs"] = re.split(r"\s*\n\s*", m[1].strip())
    return _cache["bsfs"]


#   // reversed fftools/comdutils.c show_protocols()


def protocols():
    stdout, data = _("protocols")
    if data:
        return data
    match = re.search(r"Input:\s+([\s\S]+)Output:\s+([\s\S]+)", stdout)
    _cache["protocols"] = dict(
        input=re.split(r"\s*\n\s*", match[1]), output=re.split(r"\s*\n\s*", match[1])
    )
    return _cache["protocols"]


#   // according to fftools/comdutils.c show_pix_fmts()


def pixfmts():
    stdout, data = _("pix_fmts")

    if data:
        return data

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

    _cache["pix_fmts"] = data
    return data


#   // according to fftools/comdutils.c show_sample_fmts()


def samplefmts():
    stdout, data = _("sample_fmts")
    if not data:
        _cache["sample_fmts"] = data = {
            match[1]: int(match[2]) for match in re.finditer(r"(\S+)\s+(\d+)", stdout)
        }
    return data


#   // according to fftools/comdutils.c show_layouts()


def layouts():
    stdout, data = _("layouts")
    if data:
        return data

    match = re.match(
        r"\s*Individual channels:\s+NAME\s+DESCRIPTION\s+(\S[\s\S]+)Standard channel layouts:\s+NAME\s+DECOMPOSITION\s+(\S[\s\S]+)",
        stdout,
    )
    data = dict(
        channels={
            m[1]: m[2] for m in re.finditer(r"(\S+)\s+(\s[\s\S]+?)\s*\n", match[1])
        },
        layouts={
            m[1]: m[2] for m in re.finditer(r"(\S+)\s+(\S[\s\S]+?)\s*\n", match[2])
        },
    )

    _cache["layouts"] = data
    return data


#   // according to fftools/comdutils.c show_colors()


def colors():
    stdout, data = _("colors")
    if data:
        return data

    data = {
        match[1]: match[2]
        for match in re.finditer(r"(\S+)\s+(\#[0-9a-f]{6})\s*?\n", stdout)
    }

    _cache["colors"] = data
    return data


#   // according to fftools/comdutils.c show_help_demuxer()


def demuxer_info(name):
    stdout, data = __("demuxer", name)
    if data:
        return data

    m = re.match(
        r"Demuxer (\S+) \[([^\]]+)\]:\s*?\n(?:    Common extensions: ([^.]+)\.\s*\n)?([\s\S]*)",
        stdout,
    )

    data = dict(
        name=m[1],
        long_name=m[2],
        extensions=m[3].split(",") if m[3] else [],
        options=m[4],
    )

    if not "demuxer" in _cache:
        _cache["demuxer"] = {}
    _cache["demuxer"][name] = data
    return data


#   // according to fftools/comdutils.c show_help_muxer()


def muxer_info(name):
    stdout, data = __("muxer", name)
    if data:
        return data

    m = re.match(
        r"Muxer (\S+) \[([^\]]+)\]:\s*?\n(?:    Common extensions: ([^.]+)\.\s*?\n)?(?:    Mime type: ([^.]+)\.\s*?\n)?(?:    Default video codec: ([^.]+)\.\s*?\n)?(?:    Default audio codec: ([^.]+)\.\s*?\n)?(?:    Default subtitle codec: ([^.]+).\s*?\n)?([\s\S]*)",
        stdout,
    )

    data = {
        "name": m[1],
        "long_name": m[2],
        "extensions": m[3].split(",") if m[3] else [],
        "mime_type": m[4].split(",") if m[4] else [],
        "video_codec": m[5].split(",") if m[5] else [],
        "audio_codec": m[6].split(",") if m[6] else [],
        "subtitle_codec": m[7].split(",") if m[7] else [],
        "options": m[8],
    }
    if not "muxer" in _cache:
        _cache["muxer"] = {}
    _cache["muxer"][name] = data
    return data


#   // according to fftools/comdutils.c show_help_codec()


def encoder_info(name):
    return _getCodecInfo(name, True)


def decoder_info(name):
    return _getCodecInfo(name, False)


def _getCodecInfo(name, encoder):
    stdout, data = __("encoder" if encoder else "decoder", name)
    if data:
        return data

    type = "Encoder" if encoder else "Decoder"
    m = re.search(
        type
        + r" (\S+) \[([^\]]*)\]:\s*?\n"
        + r"    General capabilities: ([^\r\n]+?)\s*?\n"
        + r"(?:    Threading capabilities: ([^\r\n]+?)\s*?\n)?"
        + r"(?:    Supported hardware devices: ([^\r\n]*?)\s*?\n)?"
        + r"(?:    Supported framerates: ([^\r\n]+?)\s*?\n)?"
        + r"(?:    Supported pixel formats: ([^\r\n]+?)\s*?\n)?"
        + r"(?:    Supported sample rates: ([^\r\n]+?)\s*?\n)?"
        + r"(?:    Supported sample formats: ([^\r\n]+?)\s*?\n)?"
        + r"(?:    Supported channel layouts: ([^\r\n]+?)\s*?\n)?"
        + r"([\s\S]*)",
        stdout,
    )

    def resolveFs(s):
        m = re.match(r"(\d+)\/ (\d+)", s)
        return [int(m[0]), int(m[1])]

    data = {
        "name": m[1],
        "long_name": m[2],
        "capabilities": m[3].split(" ") if m[3] and m[3] != "none" else [],
        "threading": m[4] if m[4] and m[4] != "none" else "",
        "supported_hwdevices": m[5].split(" ") if m[5] else [],
        "supported_framerates": map(resolveFs, m[6].split(" ")) if m[6] else [],
        "supported_pix_fmts": m[7].split(" ") if m[7] else [],
        "supported_sample_rates": m[8].split(" ") if m[8] else [],
        "supported_sample_fmts": m[9].split(" ") if m[9] else [],
        "supported_layouts": m[10].split(" ") if m[10] else [],
        "options": m[11],
    }

    if not "muxer" in _cache:
        _cache["muxer"] = {}
    _cache["muxer"][name] = data
    return data


#   // according to fftools/comdutils.c show_help_filter()


def filter_info(name):
    stdout, data = __("filter", name)
    if data:
        return data

    m = re.match(
        r"Filter (\S+)\s*?\n"
        r"(?:  (.+?)\s*?\n)?"
        r"(?:    (slice threading supported)\s*?\n)?"
        r"    Inputs:\s*?\n([\s\S]*?)(?=    Outputs)"
        r"    Outputs:\s*?\n([\s\S]*?\s*?\n)(?!S)"
        r"([\s\S]*)",
        stdout,
    )

    data = {
        "name": m[1],
        "description": m[2],
        "threading": "slice" if m[3] else "",
        "inputs": _getFilterPortInfo(m[4]),
        "outputs": _getFilterPortInfo(m[5]),
        "options": m[6],
    }

    if not "filter" in _cache:
        _cache["filter"] = {}
    _cache["filter"][name] = data
    return data


#   // according to fftools/comdutils.c show_help_bsf()


def bsfilter_info(name):
    stdout, data = __("bsf", name)
    if data:
        return data

    m = re.match(
        r"Bit stream filter (\S+)\s*?\n"
        r"(?:    Supported codecs: ([^\r\n]+?)\s*?\n)?"
        r"([\s\S]*)",
        stdout,
    )

    if stdout.startswith("Unknown"):
        raise Exception(stdout)

    data = {
        "name": m[1],
        "supported_codecs": m[2].split(" ") if m[2] else [],
        "options": m[3],
    }
    if not "filter" in _cache:
        _cache["filter"] = {}
    _cache["filter"][name] = data
    return data


def _getFilterPortInfo(str):
    if str.startswith("        none"):
        return None
    if str.startswith("        dynamic"):
        return "dynamic"

    matches = re.finditer(r"       #\d+: (\S+)(?= \() \((\S+)\)\s*?\n", str)
    if not matches:
        raise Exception("Failed to parse filter port info: %s" % str)
    return [{"name": m[1], "type": m[2]} for m in matches]


video_size_presets = {
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

frame_rate_presets = {
    "ntsc": fractions.Fraction(30000, 1001),
    "pal": fractions.Fraction(25, 1),
    "qntsc": fractions.Fraction(30000, 1001),
    "qpal": fractions.Fraction(25, 1),
    "sntsc": fractions.Fraction(30000, 1001),
    "spal": fractions.Fraction(25, 1),
    "film": fractions.Fraction(24, 1),
    "ntsc-film": fractions.Fraction(24000, 1001),
}
__all__ = [
    "filters",
    "codecs",
    "coders",
    "formats",
    "devices",
    "muxers",
    "demuxers",
    "bsfilters",
    "protocols",
    "pixfmts",
    "samplefmts",
    "layouts",
    "colors",
    "demuxer_info",
    "muxer_info",
    "encoder_info",
    "decoder_info",
    "filter_info",
    "bsfilter_info",
    "frame_rate_presets",
    "video_size_presets",
]
