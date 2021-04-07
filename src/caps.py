import subprocess
import re


def _run(args, cmd="ffmpeg", timeout=None, **kwargs):
    """Run ffmpeg and return the capture stdout.

    Raises:
        :class:`ffmpeg.Exception`: if ffprobe returns a non-zero exit code,
            an :class:`Exception` is returned with a generic error message.
            The stderr output can be retrieved by accessing the
            ``stderr`` property of the exception.
    """
    p = subprocess.Popen([cmd, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    communicate_kwargs = {}
    if timeout is not None:
        communicate_kwargs["timeout"] = timeout
    out, err = p.communicate(**communicate_kwargs)
    if p.returncode != 0:
        raise Exception("ffmpeg", out, err)
    return out.decode("utf-8")


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
    return (None, _cache[cap]) if ("cap" in _cache) else (_run(["-%s" % cap]), None)


def __(type, name):
    return (
        (None, _cache[type][name])
        if (type in _cache and name in _cache[type])
        else (_run(["--help", "%s=%s" % (type, name), "-hide_banner"]), None)
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
def showFilters():
    stdout, data = _("filters")
    if data:
        return data

    types = {"A": "audio", "V": "video", "N": "dynamic", "|": "none"}

    data = {}
    for match in _filterRegexp.finditer(stdout):
        data[match[4]] = {
            "description": match[7],
            "input": types[match[5].charAt(0)],
            "multipleInputs": match[5].length > 1,
            "output": types[match[6].charAt(0)],
            "multipleOutputs": match[6].length > 1,
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
#    * @param {Boolean} codecs.canDecode whether the codec is able to decode streams
#    * @param {Boolean} codecs.canEncode whether the codec is able to encode streams
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


def showCodecs():
    stdout, data = _("codecs")
    if data:
        return data

    data = {}
    for match in _ffCodecRegexp.finditer(stdout):
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
            "type": {"V": "video", "A": "audio", "S": "subtitle"}[match[3]],
            "description": desc,
            "canDecode": match[1] == "D",
            "decoders": decoders,
            "canEncode": match[2] == "E",
            "encoders": encoders,
            "intraFrameOnly": match[4] == "I",
            "isLossy": match[5] == "L",
            "isLossless": match[6] == "S",
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
#    * @param {Boolean} encoders.frameMT whether the encoder is able to do frame-level multithreading
#    * @param {Boolean} encoders.sliceMT whether the encoder is able to do slice-level multithreading
#    * @param {Boolean} encoders.experimental whether the encoder is experimental
#    * @param {Boolean} encoders.drawHorizBand whether the encoder supports draw_horiz_band
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


def showCoders():
    stdout, data = _(type)
    if data:
        return data

    data = {}
    for match in _coderRegexp.finditer(stdout):
        data[match[7]] = {
            "type": {"V": "video", "A": "audio", "S": "subtitle"}[match[1]],
            "description": match[8],
            "frameMT": match[2] == "F",
            "sliceMT": match[3] == "S",
            "experimental": match[4] == "X",
            "drawHorizBand": match[5] == "B",
            "directRendering": match[6] == "D",
        }

    _cache[type] = data
    return data


#   / **
#    * A callback passed to {@link FfmpegCommand  # showFormats}.
#    *
#    * @callback FfmpegCommand~formatCallback
#    * @param {Exception | null} err error object or null if no error happened
#    * @param {Object} formats format object with format names as keys and the following
#    * properties for each format:
#    * @param {String} formats.description format description
#    * @param {Boolean} formats.canDemux whether the format is able to demux streams from an input file
#    * @param {Boolean} formats.canMux whether the format is able to mux streams into an output file
#    * /

#   / **
#    * reversed fftools/comdutils.c show_formats()
#    *
#    * @method FfmpegCommand  # showFormats
#    * @category Capabilities
#    * /


def showFormats():
    return _getFormats("formats")


def showDevices():
    return _getFormats("devices")


def showMuxers():
    return _getFormats("muxers")


def showDemuxers():
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
                data[format]["canDemux"] = match[1] == "D"
                data[format]["canMux"] = match[2] == "E"

    _cache[type] = data
    return data


#   // reversed fftools/comdutils.c show_bsfs()


def showBSFilters():
    stdout, data = _("bsfs")
    if data:
        return data

    _cache["bsfs"] = re.sub(r"^\s*Bitstream filters: \s+", stdout).rstrip().split()
    return _cache["bsfs"]


#   // reversed fftools/comdutils.c show_protocols()


def showProtocols():
    stdout, data = _("protocols")
    if data:
        return data

    match = re.match(r"Input: ([\s\S]+)Output: ([\s\S]+)", stdout)
    _cache["protocols"] = {
        "input": match[1].trim().split(),
        "output": match[2].trim().split(),
    }
    return _cache["protocols"]


#   // according to fftools/comdutils.c show_pix_fmts()


def showPixFmts():
    stdout, data = _("pix_fmts")

    if data:
        return data

    data = {}
    for match in re.finditer(
        r"([I.])([O.])([H.])([P.])([B.])\s+(\S+)\s+(\d+)\s+(\d+)", stdout
    ):
        data[match[6]] = {
            "nbComponents": int(match[7]),
            "bitsPerPixel": int(match[8]),
            "input": match[1] == "I",
            "output": match[2] == "O",
            "hwAccel": match[3] == "H",
            "paletted": match[4] == "P",
            "bitstream": match[5] == "B",
        }

    _cache["pix_fmts"] = data
    return data


#   // according to fftools/comdutils.c show_sample_fmts()


def showSampleFmts():
    stdout, data = _("sample_fmts")
    if data:
        return data

    data = {}
    for match in re.finditer(r"(\S+)\s+(\d+)", stdout):
        data[match[1]] = {"depth": int(match[2])}

    _cache["sample_fmts"] = data
    return data


#   // according to fftools/comdutils.c show_layouts()


def showLayouts():
    stdout, data = _("layouts")
    if data:
        return data

    match = re.match(
        r" Individual channels: \s+NAME\s+DESCRIPTION\s+([\s\S]+)Standard channel layouts: \s+NAME\s+DECOMPOSITION\s+([\s\S]+) ",
        stdout,
    )
    data = {"channels": {}, "layouts": {}}

    for match in re.finditer(r"(\S+)\s+(.+)\s *\n\s*", match[1]):
        data["channels"][match[1]] = {"description": match[2]}
    for match in re.finditer(r"(\S+)\s+(.+)\s *\n\s*", match[2]):
        data["layouts"][match[1]] = {
            "decomposition": re.match(r"([ ^ +\s]+)", match[2])
        }

    _cache["layouts"] = data
    return data


#   // according to fftools/comdutils.c show_colors()


def showColors():
    stdout, data = _("colors")
    if data:
        return data

    data = {}
    for match in re.finditer(r"(\S+)\s+(  # [0-9a-f]{6})", stdout):
        data[match[1]] = {rgb: match[2]}

    _cache["colors"] = data
    return data


#   // according to fftools/comdutils.c show_help_demuxer()


def showDemuxerInfo(name):
    stdout, data = _("demuxer", name)
    if data:
        return data

    m = re.match(
        r" Demuxer (\S+) \[([ ^\]]+)\]: \r?\n(?:    Common extensions: ([^.]+)\.\r?\n)?([\s\S]*) ",
        stdout,
    )

    data = {
        "name": m[1],
        "long_name": m[2],
        "extensions": m[3].split(",") if m[3] else [],
        "options": m[4],
    }
    if not "demuxer" in _cache:
        _cache["demuxer"] = {}
    _cache["demuxer"][name] = data
    return data


#   // according to fftools/comdutils.c show_help_muxer()


def showMuxerInfo(name):
    stdout, data = _("muxer", name)
    if data:
        return data

    m = re.match(
        r" Muxer (\S+) \[([ ^\]]+)\]: \r?\n(?:    Common extensions: ([^.]+)\.\r?\n)?(?:    Mime type: ([^.]+)\.\r?\n)?(?:    Default video codec: ([^.]+)\.\r?\n)?(?:    Default audio codec: ([^.]+)\.\r?\n)?(?:    Default subtitle codec: ([^.]+).\r?\n)?([\s\S]*) ",
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


def showEncoderInfo(name):
    return _getCodecInfo(name, True)


def showDecoderInfo(name):
    return _getCodecInfo(name, False)


def _getCodecInfo(name, encoder):
    stdout, data = _("encoder" if encoder else "decoder", name)
    if data:
        return data

    m = re.search(
        r"%s (\\S+) \\[([^\\]]*)\\]: \\r?\\n"
        r"    General capabilities: ([^\r\n]+?) ?\r?\n"
        r"(?:    Threading capabilities: ([^\r\n]+?)\r?\n)?"
        r"(?:    Supported hardware devices: ([^\r\n]*?)\r?\n)?"
        r"(?:    Supported framerates: ([^\r\n]+?)\r?\n)?"
        r"(?:    Supported pixel formats: ([^\r\n]+?)\r?\n)?"
        r"(?:    Supported sample rates: ([^\r\n]+?)\r?\n)?"
        r"(?:    Supported sample formats: ([^\r\n]+?)\r?\n)?"
        r"(?:    Supported channel layouts: ([^\r\n]+?)\r?\n)?"
        r"([\s\S]*)" % ("Encoder" if encoder else "Decoder", stdout)
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


def showFilterInfo(name, encoder):
    stdout, data = _("filter", name)
    if data:
        return data

    m = re.match(
        r"Filter(\S+)\r?\n"
        r"(?:  (.+?)\r?\n)?"
        r"(?:    (slice threading supported)\r?\n)?"
        r"    Inputs:\r?\n([\s\S]*?)(?=    Outputs)"
        r"    Outputs:\r?\n([\s\S]*?\r?\n)(?!S)"
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


def showBsfInfo(name, encoder):
    stdout, data = _("bsf", name)
    if data:
        return data

    m = re.match(
        r"Bit stream filter(\S+)\r?\n"
        r"(?:    Supported codecs: ([^\r\n]+?)\r?\n)?"
        r"([\s\S]*)",
        stdout,
    )

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

    matches = re.finditer(r"       #\d+: (\S+)(?= \() \((\S+)\)\r?\n", str)
    if not matches:
        raise Exception("Failed to parse filter port info: %s" % str)
    return [{"name": m[1], "type": m[2]} for m in matches]


__all__ = [
    "showFilters",
    "showCodecs",
    "showCoders",
    "showFormats",
    "showDevices",
    "showMuxers",
    "showDemuxers",
    "showBSFilters",
    "showProtocols",
    "showPixFmts",
    "showSampleFmts",
    "showLayouts",
    "showColors",
    "showDemuxerInfo",
    "showMuxerInfo",
    "showEncoderInfo",
    "showDecoderInfo",
    "showFilterInfo",
    "showBsfInfo",
]

