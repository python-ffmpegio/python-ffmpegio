from ffmpegio import configure, ffmpeg, probe, utils
import pytest
import numpy as np

from ffmpegio.utils import filter as filter_utils

vid_url = "tests/assets/testvideo-1m.mp4"
img_url = "tests/assets/ffmpeg-logo.png"
aud_url = "tests/assets/testaudio-1m.wav"


def test_add_url():

    url = "test.mp4"
    args = {}
    args_expected = {}
    idx, entry = configure.add_url(args, "input", url, None)
    args_expected["inputs"] = [(url, None)]
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    idx, entry = configure.add_url(args, "input", url, {"f": "rawvideo"})
    args_expected["inputs"][0] = (url, {"f": "rawvideo"})
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    idx, entry = configure.add_url(args, "input", url, {"f": "mp4", "codec": "h264"})
    args_expected["inputs"][0] = (url, {"f": "mp4", "codec": "h264"})
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    url2 = "test2.wav"
    idx, entry = configure.add_url(args, "input", url2, {"f": "wav"})
    args_expected["inputs"].append((url2, {"f": "wav"}))
    assert idx == 1 and entry == args_expected["inputs"][1] and args == args_expected


def test_get_option():

    assert configure.get_option(None, "input", "c") is None
    assert configure.get_option({}, "input", "c") is None
    assert configure.get_option({}, "global_options", "c") is None

    args = {
        "inputs": [("file1", None)],
        "outputs": [("file2", {"c": 0, "c:v": 1, "c:v:0": 2}), ("file3", {"ac": 2})],
        "global_options": {"y": True},
    }
    assert configure.get_option(args, "global", "y") is True
    assert configure.get_option(args, "global", "n") is None
    assert configure.get_option(args, "input", "c") is None
    assert configure.get_option(args, "output", "c") == 0
    assert configure.get_option(args, "output", "c", stream_type="v") == 1
    assert configure.get_option(args, "output", "c", stream_id=0, stream_type="v") == 2
    assert configure.get_option(args, "output", "ac", file_id=1) == 2
