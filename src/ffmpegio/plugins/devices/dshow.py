""" DirectShow device"""

from subprocess import PIPE
from ffmpegio import path
import re
from pluggy import HookimplMarker
from packaging.version import Version
import logging

logger = logging.getLogger("ffmpegio")

hookimpl = HookimplMarker("ffmpegio")


def _scan():
    logs = path.ffmpeg(
        [
            "-hide_banner",
            "-f",
            "dshow",
            "-list_devices",
            "true",
            "-i",
            "dummy",
            "-loglevel",
            "repeat+info",
        ],
        stderr=PIPE,
        universal_newlines=True,
    ).stderr

    logger.debug(logs)

    sign = re.match(r"\[(.+?)\]", logs)[1]

    class TypeCounter:
        def __init__(self) -> None:
            self.v = 0
            self.a = 0

        def __call__(self, t, m):
            if m[2] is not None:
                t = m[2]
            if t == "video":
                id = f"v:{self.v}"
                self.v += 1
            else:
                id = f"a:{self.a}"
                self.a += 1
            return id

    get_id = TypeCounter()
    get_info = lambda t, name, description: {
        "media_type": t,
        "name": name,
        "description": description,
        "is_default": None,
    }

    logger.debug("For <v5.0")
    re_header = re.compile(
        rf"\[{sign}\] (?:DirectShow (.+?) devices.*|Could not enumerate .+? devices.*)\n|dummy: Immediate exit requested"
    )

    groups = [(m[1], *m.span()) for m in re_header.finditer(logs)]
    logger.debug(groups)

    re_dev = re.compile(
        rf'\[{sign}\]  "(.+?)"(?: \((.+?)\))?\n\[{sign}\]     Alternative name "(.+?)"'
    )

    return {
        get_id(media_type, m): get_info(media_type, m[1], m[3])
        for i, (media_type, _, stop) in enumerate(groups[:-1])
        if media_type in ("audio", "video")
        for m in re_dev.finditer(logs[stop : groups[i + 1][1]])
    }


def _resolve(infos):
    # TODO Verify if multiple videos/audios allowed (more than 1 each)
    return ":".join([f'{dev["media_type"]}={dev["name"]}' for dev in infos])


def _list_options(dev):
    ver = path.FFMPEG_VER
    v5_or_later = ver.is_devrelease or ver >= Version("5.0")

    is_video = dev["media_type"] == "video"

    url = f'{dev["media_type"]}={dev["name"]}'
    logs = path.ffmpeg(
        [
            "-hide_banner",
            "-f",
            "dshow",
            "-list_options",
            "true",
            "-i",
            url,
            "-loglevel",
            "repeat+info",
        ],
        stderr=PIPE,
        universal_newlines=True,
    ).stderr

    # read header
    m = re.match(rf"\[(.+?)\] DirectShow .+? device options \(from .+? devices\)", logs)
    sign = re.escape(m[1])
    i0 = m.end()

    m = re.search(
        rf"Error opening input: Immediate exit requested\n", logs
    ) or re.search(rf"{re.escape(url)}: Immediate exit requested\n", logs)
    i1 = m.start() if m else len(logs)

    re_pin = re.compile(rf'\[{sign}\]  Pin "(.+?)" \(alternative pin name "(.+?)"\)\n')

    re_video = re.compile(
        rf"\[{sign}\]   (?:unknown compression type 0x([0-9A-F]+?)|vcodec=(.+?)|pixel_format=(.+?))"
        + rf"  min s=(\d+)x(\d+) fps=([\d.]+) max s=(\d+)x(\d+) fps=([\d.]+)"
        + rf"(?: \((.+?), (.+?)/(.+?)/(.+?)(?:, (.+?))?\))?\n"
    )

    re_audio = re.compile(
        rf"\[{sign}\]   ch=\s*(\d+), bits=\s*(\d+), rate=\s*(\d+)\n"
        if v5_or_later
        else rf"\[{sign}\]   min ch=\s*(\d+) bits=\s*(\d+) rate=\s*(\d+) max ch=\s*(\d+) bits=\s*(\d+) rate=\s*(\d+)\n"
    )

    pins = [(m[1], *m.span()) for m in re_pin.finditer(logs)]
    ipins = [(pin[2], pins[i + 1][1]) for i, pin in enumerate(pins[:-1])]
    ipins.append((pins[-1][2], i1))

    device_formats = []

    for (pin, *_), (i0, i1) in zip(pins, ipins):

        def form_video_config(m):
            # https://docs.microsoft.com/en-us/windows/win32/api/strmif/nf-strmif-iamstreamconfig-getstreamcapss
            cfg = {"vcodec": m[2]} if m[2] else {"pixel_format": m[3]} if m[3] else {}
            cfg["video_pin_name"] = pin
            cfg["width"] = int(m[4])
            cfg["height"] = int(m[5])
            cfg["video_size"] = f"{m[4]}x{m[5]}"
            cfg["framerate"] = (float(m[6]), float(m[9]))
            if m[10]:
                if m[11]:
                    cfg["col_range"] = m[10]
                    cfg["col_space"] = m[11]
                    cfg["col_prim"] = m[12]
                    cfg["col_trc"] = m[13]
                    if m[14]:
                        cfg["chroma_loc"] = m[14]
                else:
                    cfg["chroma_loc"] = m[10]

            return cfg

        def form_audio_config(m):
            return (
                {
                    "audio_pin_name": pin,
                    "channels": int(m[1]),
                    "sample_size": int(m[2]),
                    "sample_rate": int(m[3]),
                }
                if v5_or_later
                else {
                    "audio_pin_name": pin,
                    "channels": (int(m[1]), int(m[4])),
                    "sample_size": (int(m[2]), int(m[5])),
                    "sample_rate": (int(m[3]), int(m[6])),
                }
            )

        re_cfgs = re_video if is_video else re_audio
        form_config = form_video_config if is_video else form_audio_config

        device_formats.extend([form_config(m) for m in re_cfgs.finditer(logs[i0:i1])])

    return device_formats


@hookimpl
def device_source_api():
    return "dshow", {
        "scan": _scan,
        "resolve": _resolve,
        "list_options": _list_options,
    }
