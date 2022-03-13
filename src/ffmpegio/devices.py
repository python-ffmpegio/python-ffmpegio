import logging
from ffmpegio.ffmpegprocess import _exec, PIPE, DEVNULL
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


    def check_plugin(plugin_devices, name, info):
        if name not in plugin_devices:
            return info

        api = plugin_devices[name]
        if info is None:
            if "rescan" in api:
                return {**api['rescan'](), **api}
            else:
                return api
        else:
            return {**info, **api}

    plugin_devices = {name: api for name, api in plugins.get_hook().device_source_api()}
    SOURCES = {
        k: check_plugin(plugin_devices, k, v) for k, v in get_devices("sources")
    }

    plugin_devices = {name: api for name, api in plugins.get_hook().device_sink_api()}
    SINKS = {
        k: check_plugin(plugin_devices, k, v) for k, v in get_devices("sinks")
    }

# def 