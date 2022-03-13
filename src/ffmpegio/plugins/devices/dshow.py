""" DirectShow device"""

from copy import deepcopy
from ffmpegio import path
from ffmpegio.ffmpegprocess import run
import re, logging
from packaging.version import Version

from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")

DSHOW_DEVICES = {}


def _list_sources():
    return deepcopy(DSHOW_DEVICES)


def _rescan():

    global DSHOW_DEVICES

    logs = run(
        {
            "inputs": [("dummy", {"f": "dshow", "list_devices": True})],
            "global_options": {"loglevel": "repeat+info"},
        },
        capture_log=True,
        universal_newlines=True,
    ).stderr

    logging.debug(logs)

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
        "dev_type": "source",
        "media_type": t,
        "name": name,
        "description": description,
        "is_default": None,
    }

    if path.FFMPEG_VER == "nightly" or path.FFMPEG_VER >= Version("5.0"):
        re_dev = re.compile(
            rf'\[{sign}\] "(.+?)" \((.+?)\)\n\[{sign}\]   Alternative name "(.+?)"|dummy: Immediate exit requested'
        )

        devices = {}
        for m in re_dev.finditer(logs):
            if m[1] is None:
                break
            name = m[1]
            description = m[3]
            for media_type in m[2].split(","):
                if media_type in ("video", "audio"):
                    devices[get_id(media_type, m)] = get_info(
                        media_type, name, description
                    )

        DSHOW_DEVICES = devices
    else:
        logging.info("Earlier FFmpeg version found")
        re_header = re.compile(
            rf"\[{sign}\] (?:DirectShow (.+?) devices.*|Could not enumerate .+? devices.*)\n|dummy: Immediate exit requested"
        )

        groups = [(m[1], *m.span()) for m in re_header.finditer(logs)]
        logging.debug(groups)

        re_dev = re.compile(
            rf'\[{sign}\]  "(.+?)"(?: \((.+?)\))?\n\[{sign}\]     Alternative name "(.+?)"'
        )

        DSHOW_DEVICES = {
            get_id(media_type, m): get_info(media_type, m[1], m[3])
            for i, (media_type, _, stop) in enumerate(groups[:-1])
            if media_type in ("audio", "video")
            for m in re_dev.finditer(logs[stop : groups[i + 1][1]])
        }


def _resolve(dev_type, url):
    if dev_type != "source":
        raise ValueError(
            f"Invalid dev_type ({dev_type}). DirectShow (dshow) device only supports source devices."
        )
    try:
        url = ":".join(
            [
                f'{dev["media_type"]}="{dev["name"]}"'
                for dev in (DSHOW_DEVICES[spec] for spec in url.split("|"))
            ]
        )
    finally:
        return url


def _get_dev(dev_type, spec):
    if dev_type != "source":
        raise ValueError(
            f"Invalid dev_type ({dev_type}). DirectShow (dshow) device only supports source devices."
        )

    # get the device
    try:
        dev = DSHOW_DEVICES[spec]
    except:
        # look for the names
        try:
            dev = next(
                (
                    v
                    for v in DSHOW_DEVICES.values()
                    if v["name"] == spec or v["description"] == spec
                )
            )
        except:
            raise ValueError(
                f"Specified DirectShow device ({spec}) does not exist. Run `ffmpegio.devices.rescan()` and try again."
            )
    return dev


def _list_options(dev_type, spec):

    dev = _get_dev(dev_type, spec)

    is_video = dev["media_type"] == "video"

    url = f'{dev["media_type"]}={dev["name"]}'
    logs = run(
        {
            "inputs": [(url, {"f": "dshow", "list_options": True})],
            "global_options": {"loglevel": "repeat+info"},
        },
        capture_log=True,
        universal_newlines=True,
    ).stderr

    # read header
    m = re.match(rf"\[(.+?)\] DirectShow .+? device options \(from .+? devices\)", logs)
    sign = re.escape(m[1])
    i0 = m.end()

    m = re.search(fr"{re.escape(url)}: Immediate exit requested\n$", logs)
    i1 = m.start()

    re_pin = re.compile(rf'\[{sign}\]  Pin "(.+?)" \(alternative pin name "(.+?)"\)\n')
    pins = [(m[1], *m.span()) for m in re_pin.finditer(logs)]
    ipins = [(pin[2], pins[i + 1][1]) for i, pin in enumerate(pins[:-1])]
    ipins.append((pins[-1][2], i1))

    device_formats = []

    for (pin, *_), (i0, i1) in zip(pins, ipins):

        re_video = re.compile(
            rf"\[{sign}\]   (?:unknown compression type 0x([0-9A-F]+?)|vcodec=(.+?)|pixel_format=(.+?))"
            + rf"  min s=(\d+)x(\d+) fps=([\d.]+) max s=(\d+)x(\d+) fps=([\d.]+)"
            + rf"(?: \((.+?), (.+?)/(.+?)/(.+?)(?:, (.+?))?\))?\n"
        )

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

        re_audio = re.compile(
            rf"\[{sign}\]   ch=\s*(\d+), bits=\s*(\d+), rate=\s*(\d+)\n"
        )

        def form_audio_config(m):
            return {
                "audio_pin_name": pin,
                "channels": int(m[1]),
                "sample_size": int(m[2]),
                "sample_rate": int(m[3]),
            }

        re_cfgs = re_video if is_video else re_audio
        form_config = form_video_config if is_video else form_audio_config

        device_formats.extend([form_config(m) for m in re_cfgs.finditer(logs[i0:i1])])

    return device_formats


@hookimpl
def device_source_api():
    return "dshow", {
        "rescan": _rescan,
        "list_sources": _list_sources,
        "resolve": _resolve,
        "list_options": _list_options,
    }
