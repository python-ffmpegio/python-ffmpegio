import logging
from ffmpegio.path import _exec
from subprocess import PIPE, DEVNULL
from . import plugins
import re

SOURCES = {}
SINKS = {}


def rescan():

    global SOURCES, SINKS

    def get_devices(dev_type):
        out = _exec(
            f"-{dev_type}",
            stderr=DEVNULL,
            stdout=PIPE,
            universal_newlines=True,
        )

        logging.debug(f"ffmpeg -{dev_type}")
        logging.debug(out.stdout)

        src_spans = [
            [m[1], *m.span()]
            for m in re.finditer(fr"Auto-detected {dev_type} for (.+?):\n", out.stdout)
        ]
        for i in range(len(src_spans) - 1):
            src_spans[i][1] = src_spans[i][2]
            src_spans[i][2] = src_spans[i + 1][1]
        src_spans[-1][1] = src_spans[-1][2]
        src_spans[-1][2] = len(out.stdout)

        def parse(log):
            # undoing print_device_list() in fftools/cmdutils.c
            if log.startswith(f"Cannot list {dev_type}"):
                return None
            devices = {}
            counts = {"audio": 0, "video": 0}
            for m in re.finditer(r"([ *]) (.+?) \[(.+?)\] \((.+?)\)\n", log):
                info = {
                    "name": m[2],
                    "description": m[3],
                    "is_default": m[1] == "*" or None,
                }
                media_types = m[4].split(",")
                for media_type in media_types:
                    if media_type in ("video", "audio"):
                        spec = f"{media_type[0]}:{counts[media_type]}"
                        counts[media_type] += 1
                        devices[spec] = {**info, "media_type": media_type}
            return devices

        return [(name, parse(out.stdout[i0:i1])) for name, i0, i1 in src_spans]

    def gather_device_info(dev_type, hook):
        plugin_devices = {
            name: api for name, api in getattr(plugins.get_hook(), hook)()
        }
        devs = {}
        for key, devlist in get_devices(dev_type):
            names = key.split(",")  # may have alias

            name = names[0]  # plugin must be defined for the base name
            if name in plugin_devices:
                info = plugin_devices[name]
                if devlist is not None:
                    info["list"] = devlist
                elif "rescan" in info:
                    info["list"] = info["rescan"]()
            else:
                info = {"list": devlist} if devlist else None

            if info is not None:
                for name in names:
                    devs[name] = info
        return devs

    SOURCES = gather_device_info("sources", "device_source_api")
    SINKS = gather_device_info("sinks", "device_sink_api")


def _list_devices(devs, mtype):
    return [
        dev
        for dev, info in devs.items()
        if "list" in info and any((k.startswith(mtype) for k in info["list"].keys()))
    ]


def list_video_sources():
    return _list_devices(SOURCES, "v")


def list_audio_sources():
    return _list_devices(SOURCES, "a")


def list_video_sinks():
    return _list_devices(SINKS, "v")


def list_audio_sinks():
    return _list_devices(SINKS, "a")

def resolve_source(url, opts):
    try:
        dev = SOURCES[opts["f"]]
        assert dev is not None
    except:
        # not a device or unknown device
        return url, opts

    try:
        return dev["resolve"]("source", url), opts
    except:
        try:
            url = dev["list"][url]
        finally:
            return url, opts


def resolve_sink(url, opts):
    try:
        dev = SINKS[opts["f"]]
        assert dev is not None
    except:
        # not a device or unknown device
        return url, opts

    try:
        return dev["resolve"]("sink", url), opts
    except:
        try:
            url = dev["list"][url]
        finally:
            return url, opts
