from ffmpegio import configure

vid_url = "tests/assets/testvideo-1m.mp4"
img_url = "tests/assets/ffmpeg-logo.png"
aud_url = "tests/assets/testaudio-1m.wav"


def test_array_to_audio_input():
    fs = 44100
    N = 44100
    nchmax = 4
    data = {"buffer": b"0" * N * nchmax * 2, "dtype": "<i2", "shape": (nchmax,)}

    cfg = {"f": "s16le", "c:a": "pcm_s16le", "ac": 4, "ar": 44100, "sample_fmt": "s16"}
    input = configure.array_to_audio_input(fs, data)
    assert input[0] == "-" and input[1] == cfg


def test_array_to_video_input():
    fs = 30
    dtype = "|u1"
    h = 360
    w = 480
    ncomp = 3
    nframes = 10
    data = {
        "buffer": b"0" * nframes * h * w * ncomp,
        "dtype": dtype,
        "shape": (nframes, h, w, ncomp),
    }
    cfg = {
        "f": "rawvideo",
        "c:v": "rawvideo",
        "s": (w, h),
        "r": fs,
        "pix_fmt": "rgb24",
    }

    input = configure.array_to_video_input(fs, data)
    print(input)
    assert input[0] == "-" and input[1] == cfg


def test_add_url():

    url = "test.mp4"
    args = {}
    args_expected = {}
    idx, entry = configure.add_url(args, "input", url, None)
    args_expected["inputs"] = [(url, None)]
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    idx, entry = configure.add_url(args, "input", url, {"f": "rawvideo"}, update=True)
    args_expected["inputs"][0] = (url, {"f": "rawvideo"})
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    idx, entry = configure.add_url(
        args, "input", url, {"f": "mp4", "codec": "h264"}, update=True
    )
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


def test_video_basic_filter():
    print(
        configure._build_video_basic_filter(
            fill_color=None,
            remove_alpha=None,
            crop=None,
            flip=None,
            transpose=None,
        )
    )
    print(
        configure._build_video_basic_filter(
            fill_color="red",
            remove_alpha=True,
            # crop=(100, 100, 5, 10),
            # flip="horizontal",
            # transpose="clock",
        )
    )
