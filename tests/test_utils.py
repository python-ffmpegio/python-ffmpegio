from ffmpegio import utils
import pytest
import numpy as np


def test_parse_spec_stream():
    assert utils.parse_spec_stream(1) == {"index": 1}
    assert utils.parse_spec_stream("1") == {"index": 1}
    assert utils.parse_spec_stream("v") == {"type": "v"}
    assert utils.parse_spec_stream("p:1") == {"program_id": 1}
    assert utils.parse_spec_stream("p:1:V") == {"program_id": 1, "type": "V"}
    assert utils.parse_spec_stream("p:1:a:#6") == {
        "program_id": 1,
        "type": "a",
        "pid": 6,
    }
    assert utils.parse_spec_stream("d:i:6") == {"type": "d", "pid": 6}
    assert utils.parse_spec_stream("t:m:key") == {"type": "t", "tag": "key"}
    assert utils.parse_spec_stream("m:key:value") == {"tag": ("key", "value")}
    assert utils.parse_spec_stream("u") == {"usable": True}


def test_spec_stream():
    assert utils.spec_stream() == ""
    assert utils.spec_stream(0) == "0"
    assert utils.spec_stream(type="a") == "a"
    assert utils.spec_stream(1, type="v") == "v:1"
    assert utils.spec_stream(program_id="1") == "p:1"
    assert utils.spec_stream(1, type="v", program_id="1") == "v:p:1:1"
    assert utils.spec_stream(pid=342) == "#342"
    assert utils.spec_stream(tag="creation_time") == "m:creation_time"
    assert (
        utils.spec_stream(tag=("creation_time", "2018-05-26T19:36:24.000000Z"))
        == "m:creation_time:2018-05-26T19:36:24.000000Z"
    )
    assert utils.spec_stream(usable=True) == "u"


def test_get_pixel_config():
    with pytest.raises(Exception):
        utils.get_pixel_config("yuv")  # unknown format
    cfg = utils.get_pixel_config("rgb24")  # unknown format
    assert cfg[0] == "rgb24" and cfg[1] == 3 and cfg[2] == "|u1"


def test_alpha_change():

    cases = (("rgb24", "rgba", 1), ("rgb24", "rgb24", 0), ("ya8", "gray", -1))

    for input_pix_fmt, output_pix_fmt, dir in cases:
        dout = utils.alpha_change(input_pix_fmt, output_pix_fmt)
        assert dir == dout
        assert utils.alpha_change(input_pix_fmt, output_pix_fmt, dir) is True
        if dir:
            assert utils.alpha_change(input_pix_fmt, output_pix_fmt, -dir) is False
            assert utils.alpha_change(input_pix_fmt, output_pix_fmt, 0) is False
        else:
            assert utils.alpha_change(input_pix_fmt, output_pix_fmt, 1) is False
            assert utils.alpha_change(input_pix_fmt, output_pix_fmt, -1) is False


def test_get_rotated_shape():
    w = 1000
    h = 400
    print(utils.get_rotated_shape(w, h, 30))
    print(utils.get_rotated_shape(w, h, 45))
    print(utils.get_rotated_shape(w, h, 60))
    assert utils.get_rotated_shape(w, h, 90) == (h, w, np.pi / 2.0)


def test_get_audio_codec():
    cfg = utils.get_audio_codec("s16")
    assert cfg[0] == "pcm_s16le" and cfg[1] == "s16le"


def test_get_audio_format():
    cfg = utils.get_audio_format("s16", 2)
    assert cfg[0] == "<i2" and cfg[1] == (2,)


def test_array_to_audio_input():
    fs = 44100
    N = 44100
    nchmax = 4
    data = {"buffer": b"0" * N * nchmax * 2, "dtype": "<i2", "shape": (nchmax,)}

    cfg = {"f": "s16le", "c:a": "pcm_s16le", "ac": 4, "ar": 44100, "sample_fmt": "s16"}
    input = utils.array_to_audio_input(fs, data)
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

    input = utils.array_to_video_input(fs, data)
    print(input)
    assert input[0] == "-" and input[1] == cfg


if __name__ == "__main__":
    import re

    spec = "p:4"
    print(re.split(r"(?<![pi]\:|m\:.+?\:)\:", spec))
