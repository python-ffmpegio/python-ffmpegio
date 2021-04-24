from ffmpegio import configure, ffmpeg, probe, filter_utils, utils
import pytest
import numpy as np

vid_url = "tests/assets/testvideo-5m.mpg"
img_url = "tests/assets/ffmpeg-logo.png"
aud_url = "tests/assets/testaudio-one.wav"


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


def test_finalize_opts():
    input = dict(a=0, b=1, c=2)
    opt_names = ["a", "c", "d"]
    assert configure.finalize_opts(input, opt_names) == dict(a=0, c=2)

    default = dict(a=5, d=3)
    assert configure.finalize_opts(input, opt_names, default) == dict(a=0, c=2, d=3)

    prefix = "video_"
    video_input = {(prefix + k): v for k, v in input.items()}
    assert configure.finalize_opts(video_input, opt_names, prefix=prefix) == dict(
        a=0, c=2
    )

    aliases = {"e": "a"}
    assert configure.finalize_opts(
        {**input, "e": 5}, opt_names, aliases=aliases
    ) == dict(a=5, c=2)


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


def test_input_timing():
    args = configure.input_timing(vid_url)
    args_expected = {
        "inputs": [("tests/assets/testvideo-5m.mpg", {})],
        "outputs": [],
        "global_options": None,
    }
    assert args == args_expected

    opts = args_expected["inputs"][0][1]

    args = configure.input_timing(vid_url, input_frame_rate=2000)
    opts["r:v"] = 2000
    assert args == args_expected

    args = configure.input_timing(
        vid_url, vstream_id=0, input_frame_rate=1000, ffmpeg_args=args
    )
    opts["r:v:0"] = 1000
    assert args == args_expected

    args = configure.input_timing(vid_url, start=0.1, ffmpeg_args=args)
    opts["ss"] = 0.1
    assert args == args_expected

    args = configure.input_timing(vid_url, end=0.5, ffmpeg_args=args)
    opts["to"] = 0.5
    assert args == args_expected

    args = configure.input_timing(vid_url, duration=1.0, ffmpeg_args=args)
    opts["t"] = 1.0
    assert args == args_expected

    args = configure.input_timing(vid_url, start=1, units="frames", ffmpeg_args=args)
    opts["ss"] = 1 / 2000
    assert args == args_expected

    args = configure.input_timing(
        vid_url, start=1, units="frames", vstream_id=0, ffmpeg_args=args
    )
    opts["ss"] = 1 / 1000
    assert args == args_expected

    args = configure.input_timing(
        vid_url,
        start=1,
        units="samples",
        astream_id=0,
        input_sample_rate=8000,
        ffmpeg_args=args,
    )
    opts["ar:a:0"] = 8000
    opts["ss"] = 1 / 8000
    assert args == args_expected


def test_codec():
    args = configure.codec(vid_url, "v")
    args_expected = {
        "inputs": [],
        "outputs": [("tests/assets/testvideo-5m.mpg", {})],
        "global_options": None,
    }
    opts = args_expected["outputs"][0][1]
    assert args == args_expected

    args = configure.codec(vid_url, "v", codec="h264")
    opts["c:v"] = "h264"
    assert args == args_expected

    args = configure.codec(vid_url, "a", codec="none", ffmpeg_args=args)
    opts["an"] = None
    assert args == args_expected


def test_audio_stream():
    info = {"sample_rate": 44100, "sample_fmt": "s16", "channels": 2}
    stream_opts = {"sample_rate": 48000, "sample_fmt": "s32", "channels": 1}
    assert configure.audio_stream(info) == ({}, None)
    assert configure.audio_stream(info, for_reader=True) == (
        {"codec": "pcm_s16le"},
        (np.int16, 2, 44100),
    )
    assert configure.audio_stream(info, *(stream_opts,)) == (
        {"ar": 48000, "sample_fmt": "s32", "ac": 1},
        None,
    )

