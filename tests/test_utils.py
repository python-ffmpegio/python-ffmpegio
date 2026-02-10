import pytest

from ffmpegio import utils


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


def test_get_pixel_config():
    with pytest.raises(Exception):
        utils.get_pixel_config("yuv")  # unknown format
    cfg = utils.get_pixel_config("rgb24")  # unknown format
    assert cfg[0] == "rgb24" and cfg[1] == 3 and cfg[2] == "|u1"


def test_get_pixel_format():

    with pytest.raises(KeyError):
        utils.get_pixel_format("yuv")  # unknown format
    cfg = utils.get_pixel_format("rgb24")  # unknown format
    assert cfg[1] == 3 and cfg[0] == "|u1"

    with pytest.raises(ValueError):
        utils.get_pixel_format("yuv420p")
    cfg = utils.get_pixel_format("yuv444p")  # unknown format
    assert cfg[0] == "|u1" and cfg[1] == 3


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


def test_get_audio_codec():
    cfg = utils.get_audio_codec("s16")
    assert cfg[0] == "pcm_s16le" and cfg[1] == "s16le"


def test_get_audio_format():
    cfg = utils.get_audio_format("s16", 2)
    assert cfg[0] == "<i2" and cfg[1] == (2,)


def test_analyze_output_video_filter():
    res = utils.analyze_output_video_filter(
        "format=yuv420p,scale=320:240,framerate=100",
        30,
        "rgb24",
        (
            1920,
            1080,
        ),
    )
    assert res == (100, "yuv420p", (320, 240))
