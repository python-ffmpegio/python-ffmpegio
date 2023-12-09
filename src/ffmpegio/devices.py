"""I/O Device Enumeration Module

This module allows input and output hardware devices to be enumerated in the same fashion as the 
streams of media containers. For example, instead of specifying DirectShow hardware by

```
url = 'video="WebCam":audio="Microphone"'
```

You can specify them as

```
url = 'v:0|a:0'
```


"""
import logging

logger = logging.getLogger("ffmpegio")

from ffmpegio.path import ffmpeg
from subprocess import PIPE, DEVNULL
from . import plugins
import re

SOURCES = {}
SINKS = {}


def scan():
    """scans the system for input/output hardware

    This function must be called by user to enable device enumeration in
    ffmpegio. Also, none of functions in `ffmpegio.devices` module will return
    meaningful outputs until `scan` is called. Likewise, `scan()` must
    run again after a change in hardware to reflect the change.

    The devices are enumerated according to the outputs of outputs
    `ffmpeg -sources` and `ffmpeg -sinks` calls for the devices supporting
    this fairly new FFmpeg interface. Additional hardware configurations
    are detected by registered plugins with hooks `device_source_api` or
    `device_sink_api`.

    Currently Supported Devices
    ---------------------------
    Windows: dshow
    Mac: tbd
    Linux: tbd
    """

    global SOURCES, SINKS

    def get_devices(dev_type):
        out = ffmpeg(
            f"-{dev_type}",
            stderr=DEVNULL,
            stdout=PIPE,
            universal_newlines=True,
        )

        logger.debug(f"ffmpeg -{dev_type}")
        logger.debug(out.stdout)

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
                elif "scan" in info:
                    info["list"] = info["scan"]()
            else:
                info = {"list": devlist} if devlist else None

            if info is not None:
                for name in names:
                    devs[name] = info
        return devs

    SOURCES = gather_device_info("sources", "device_source_api")
    SINKS = gather_device_info("sinks", "device_sink_api")


def _list_devices(devs, dev, mtype, return_nested):
    if mtype:
        mtype = mtype[0]
    return (
        {
            d: {
                k: v["name"]
                for k, v in devs.get(d, {}).get("list", {}).items()
                if not mtype or mtype == k[0]
            }
            for d in (devs.keys() if dev is None else [dev])
        }
        if return_nested or dev
        else {
            (d, k): v["name"]
            for d in (devs.keys() if dev is None else [dev])
            for k, v in devs.get(d, {}).get("list", {}).items()
            if not mtype or mtype == k[0]
        }
    )


def list_sources(dev=None, mtype=None, return_nested=False):
    """list enumerated source hardware devices

    :param dev: ffmpeg device name, defaults to None
    :type dev: str, optional
    :param mtype: media type, defaults to None
    :type dev: "video", "audio", optional
    :param return_nested: True to return results in nested dict, defaults to False
    :type return_nested: bool, optional
    :returns: dict of names of supported hardware, keyed by a tuple of the device name and enumeration,
              or nested dicts. If dev is specified, dict of enumerated hardware devices and their names
    :rtype: dict(tuple(str,str),str) or dict(str,dict(str,str)) or dict(str,str)
    """
    devs = _list_devices(SOURCES, dev, mtype, return_nested)
    return devs[dev] if dev else devs


def list_sinks(dev=None, mtype=None, return_nested=False):
    """list enumerated sink hardware devices

    :param dev: ffmpeg device name, default to None
    :type dev: str, optional
    :param mtype: media type, default to None
    :type dev: "video", "audio", optional
    :param return_nested: True to return results in nested dict, defaults to False
    :type return_nested: bool, optional
    :returns: dict of names of supported hardware, keyed by a tuple of the device name and enumeration,
              or nested dicts. If dev is specified, dict of enumerated hardware devices and their names
    :rtype: dict(tuple(str,str),str) or dict(str,dict(str,str)) or dict(str,str)
    """
    devs = _list_devices(SINKS, dev, mtype, return_nested)
    return devs[dev] if dev else devs


def _get_dev(device, dev_type):
    try:
        devices = dev_type and {"source": SOURCES, "sink": SINKS}[dev_type]
    except:
        raise ValueError(f'Unknown dev_type: {dev_type} (must be "source" or "sink") ')

    try:
        if devices:
            return devices[device]
        else:
            try:
                return SOURCES[device]
            except:
                return SINKS[device]
    except:
        raise ValueError(f"Unknown/unenumerated device: {device}")


def get_source_info(device, enum):
    """get source information

    :param device: device name
    :type device: str
    :param enum: hardware enumeration
    :type enum: str
    :return: info dict with keys: name, description, and is_default
    :rtype: dict[str,str]
    """

    info = _get_dev(device, "source")
    try:
        return {k: info["list"][enum][k] for k in ("name", "description", "is_default")}
    except:
        raise ValueError(f"Source device {device}:{enum} is not found ")


def get_sink_info(device, enum):
    """get sink information

    :param device: device name
    :type device: str
    :param enum: hardware enumeration
    :type enum: str
    :return: info dict with keys: name, description, and is_default
    :rtype: dict[str,str]
    """

    info = _get_dev(device, "sink")
    try:
        return {k: info["list"][enum][k] for k in ("name", "description", "is_default")}
    except:
        raise ValueError(f"Sink device {device}:{enum} is not found ")


# TODO find_source() and find_sink() given device name or description


def list_source_options(device, enum):
    """list supported options of enumerated source hardware

    :param device: device name
    :type device: str
    :param enum: hardware specifier, e.g., v:0, a:0
    :type enum: str
    :return: list of supported option combinations. If option values are tuple
             it indicates the min and max range of the option value.
    :rtype: list[dict]
    """
    dev = _get_dev(device, "source")
    try:
        list_options = dev["list_options"]
    except:
        raise ValueError(f"No options to list")
    return list_options(dev["list"][enum])


def list_sink_options(device, enum):
    """list supported options of enumerated sink hardware

    :param device: device name
    :type device: str
    :param enum: hardware specifier, e.g., v:0, a:0
    :type enum: str
    :return: list of supported option combinations. If option values are tuple
             it indicates the min and max range of the option value.
    :rtype: list[dict]
    """
    info = _get_dev(device, "sink")
    try:
        list_options = info["list_options"]
    except:
        raise ValueError(f"No options to list")
    return list_options("sink", enum)


def _resolve(devs, url, opts):
    try:
        # try to get device name
        try:
            f = opts["f"]
            _opts = opts
            _url = url
        except:
            # use the first part of the device name
            f, _url = url.split(":", 1)
            try:
                _opts = {**opts, "f": f}
            except:
                _opts = {"f": f}
        # try to get device info
        dev = devs[f]
        assert dev is not None
    except:
        # not a device or unknown device
        return url, opts

    # find device names
    try:
        enums = {enum for enum in _url.split("|")}
        infos = [dev["list"][enum] for enum in enums]
    except:
        # unknown enumeration (possibly the actual name)
        return url, opts

    try:
        # if device-specific resolver is available, use it
        return dev["resolve"](infos), _opts
    except:
        # only allow single stream
        if len(infos) > 1:
            raise ValueError(f"{f} only supports 1 enumerated hardware device per url")
        return infos[0]["name"], opts


def resolve_source(url, opts):
    """resolve source enumeration

    :param url: input url, possibly device enum
    :type url: str
    :param opts: input options
    :type opts: dict
    :return: possibly modified url and opts
    :rtype: tuple[str,dict]

    This function is called by `ffmpeg.compose()` to convert
    device enumeration back to url expected by ffmpeg

    The device name (-f) could be provided via opts['f'] or encoded as a
    part of enumeration

    """
    return _resolve(SOURCES, url, opts)


def resolve_sink(url, opts):
    """resolve sink enumeration

    :param url: output url, possibly device enum
    :type url: str
    :param opts: output options
    :type opts: dict
    :return: possibly modified url and opts
    :rtype: tuple[str,dict]

    This function is called by `ffmpeg.compose()` to convert
    device enumeration back to url expected by ffmpeg

    """
    return _resolve(SINKS, url, opts)
