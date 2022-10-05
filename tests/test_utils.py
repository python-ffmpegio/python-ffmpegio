import math
from ffmpegio import utils
import pytest


def test_string_escaping():
    raw = "Crime d'Amour"
    esc = utils.escape(raw)
    assert esc == r"'Crime d'\''Amour'"
    assert utils.unescape(esc) == raw

    raw = "  this string starts and ends with whitespaces  "
    esc = utils.escape(raw)
    assert esc == "'  this string starts and ends with whitespaces  '"
    assert utils.unescape(esc) == raw

    esc = r"' The string '\'string\'' is a string '"
    raw = r" The string 'string' is a string "
    assert raw == utils.unescape(utils.escape(raw))
    assert raw == utils.unescape(esc)

    esc = r"'c:\foo' can be written as c:\\foo"
    raw = r"c:\foo can be written as c:\foo"
    assert raw == utils.unescape(esc)
    assert raw == utils.unescape(utils.escape(raw))

    raw = "d'Amour"
    esc = utils.escape(raw)
    assert esc == r"d\'Amour"
    assert utils.unescape(esc) == raw

    raw = r"c:\foo"
    esc = utils.escape(raw)
    assert esc == r"c:\\foo"
    assert utils.unescape(esc) == raw


def test_parse_stream_spec():
    assert utils.parse_stream_spec(1) == {"index": 1}
    assert utils.parse_stream_spec("1") == {"index": 1}
    assert utils.parse_stream_spec("v") == {"type": "v"}
    assert utils.parse_stream_spec("p:1") == {"program_id": 1}
    assert utils.parse_stream_spec("p:1:V") == {"program_id": 1, "type": "V"}
    assert utils.parse_stream_spec("p:1:a:#6") == {
        "program_id": 1,
        "type": "a",
        "pid": 6,
    }
    assert utils.parse_stream_spec("d:i:6") == {"type": "d", "pid": 6}
    assert utils.parse_stream_spec("t:m:key") == {"type": "t", "tag": "key"}
    assert utils.parse_stream_spec("m:key:value") == {"tag": ("key", "value")}
    assert utils.parse_stream_spec("u") == {"usable": True}

    assert utils.parse_stream_spec("0:1", True) == {"index": 1, "file_index": 0}
    assert utils.parse_stream_spec([0, 1], True) == {"index": 1, "file_index": 0}


def test_stream_spec():
    assert utils.stream_spec() == ""
    assert utils.stream_spec(0) == "0"
    assert utils.stream_spec(type="a") == "a"
    assert utils.stream_spec(1, type="v") == "v:1"
    assert utils.stream_spec(program_id="1") == "p:1"
    assert utils.stream_spec(1, type="v", program_id="1") == "v:p:1:1"
    assert utils.stream_spec(pid=342) == "#342"
    assert utils.stream_spec(tag="creation_time") == "m:creation_time"
    assert (
        utils.stream_spec(tag=("creation_time", "2018-05-26T19:36:24.000000Z"))
        == "m:creation_time:2018-05-26T19:36:24.000000Z"
    )
    assert utils.stream_spec(usable=True) == "u"


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
    assert utils.get_rotated_shape(w, h, 90) == (h, w, math.pi / 2.0)


def test_get_audio_codec():
    cfg = utils.get_audio_codec("s16")
    assert cfg[0] == "pcm_s16le" and cfg[1] == "s16le"


def test_get_audio_format():
    cfg = utils.get_audio_format("s16", 2)
    assert cfg[0] == "<i2" and cfg[1] == (2,)


if __name__ == "__main__":
    import re
