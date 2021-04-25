from ffmpegio import utils, caps
import pytest
import numpy as np


def test_spec_stream():
    assert utils.spec_stream() == ""
    assert utils.spec_stream(0) == "0"
    assert utils.spec_stream(type="a") == "a"
    assert utils.spec_stream(1, type="v") == "v:1"
    assert utils.spec_stream(program_id="1") == "p:1"
    assert utils.spec_stream(1, type="v", program_id="1") == "p:1:v:1"
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
    assert cfg[0] == "rgb24" and cfg[1] == 3 and cfg[2] == np.uint8


def test_get_rotated_shape():
    w = 1000
    h = 400
    print(utils.get_rotated_shape(w, h, 30))
    print(utils.get_rotated_shape(w, h, 45))
    print(utils.get_rotated_shape(w, h, 60))
    assert utils.get_rotated_shape(w, h, 90) == (h, w)


def test_get_audio_format():
    cfg = utils.get_audio_format("s16")
    assert cfg[0] == "pcm_s16le" and cfg[1] == np.int16
    cfg = utils.get_audio_format(np.int16)
    assert cfg[0] == "pcm_s16le" and cfg[1] == "s16"


def test_array_to_audio_input():
    fs = 44100
    N = 44100
    nchmax = 4
    ii16 = np.iinfo(np.int16)
    data = np.random.randint(ii16.min, high=ii16.max, size=(N, nchmax), dtype=np.int16)
    sample = np.random.randint(ii16.min, high=ii16.max, size=(nchmax), dtype=np.int16)

    cfg = {"c:a": "pcm_s16le", "ac:a": 4, "ar:a": 44100, "sample_fmt:a": "s16"}
    input = utils.array_to_audio_input(fs, sample)
    assert input[0] == "-" and input[1] == cfg

    cfg = {"c:a": "pcm_s16le", "ac:a": 4, "ar:a": 44100, "sample_fmt:a": "s16"}
    input = utils.array_to_audio_input(fs, data)
    assert input[0] == "-" and input[1] == cfg

    cfg = {"c:a:0": "pcm_s16le", "ac:a:0": 4, "ar:a:0": 44100, "sample_fmt:a:0": "s16"}
    input = utils.array_to_audio_input(fs, data, 0)
    assert input[0] == "-" and input[1] == cfg

    input = utils.array_to_audio_input(fs, data, 0, format="avi")
    cfg["f"] = "avi"
    assert input[0] == "-" and input[1] == cfg

    cfg = {"c:a:1": "pcm_s16le", "ac:a:1": 4, "ar:a:1": 44100, "sample_fmt:a:1": "s16"}
    input = utils.array_to_audio_input(fs, data, 1)
    assert input[0] == "-" and input[1] == cfg

    cfg = {"c:a:1": "pcm_s16le", "ac:a:1": 4, "ar:a:1": 44100, "sample_fmt:a:1": "s16"}
    with pytest.raises(Exception):
        # no sample_fmt or channels
        input = utils.array_to_audio_input(fs, data, 1, codec="mp3")

    cfg["c:a:1"] = "mp3"
    input = utils.array_to_audio_input(
        fs, data, 1, codec="mp3", channels=4, sample_fmt="s16"
    )
    assert input[0] == "-" and input[1] == cfg


def test_analyze_audio_input():

    assert utils.analyze_audio_input(("-", None))[0] == [{}]

    cfgs,always_copy = utils.analyze_audio_input(
        (
            "-",
            {
                "c:a:0": "pcm_s16le",
                "c:a:1": "pcm_s32le",
                "ac:a:0": "4",
                "ac:a:1": 2,
                "ar:a:0": "44100",
                "ar:a:1": 96000,
                "sample_fmt:a:1": "s32",
                "sample_fmt:a": "s16",
            },
        )
    )
    assert cfgs[0] == {
        "codec_name": "pcm_s16le",
        "channels": 4,
        "sample_rate": 44100,
        "sample_fmt": "s16",
    }
    assert cfgs[1] == {
        "codec_name": "pcm_s32le",
        "channels": 2,
        "sample_rate": 96000,
        "sample_fmt": "s32",
    }


@pytest.fixture(scope="module", params=["rgb24", "rgba", "gray", "ya8"])
def image_spec(request):
    return (1920, 1080), request.param


@pytest.fixture(
    scope="module",
    params=[
        (True, True, True),
        (True, True, False),
        (False, True, True),
        (False, True, False),
    ],
)
def video_data(request, image_spec):
    size, pix_fmt = image_spec

    dtype = np.uint8
    ncomp = {"rgb24": 3, "rgba": 4, "gray": 1, "ya8": 2}[pix_fmt]

    iiu8 = np.iinfo(dtype)
    size = ((10,), size[::-1], (ncomp,))
    picker = request.param
    if ncomp == 1 or picker[2]:
        shape = [s for i, ss in enumerate(size) if picker[i] for s in ss]
        yield np.random.randint(iiu8.min, high=iiu8.max, size=shape, dtype=dtype)
    else:
        pytest.skip()


def test_array_to_video_input(video_data, image_spec):
    fs = 30
    size, pix_fmt = image_spec
    size_str = f"{size[0]}x{size[1]}"

    cfg = {"c:v": "rawvideo", "s:v": size_str, "r:v": fs, "pix_fmt:v": pix_fmt}

    input = utils.array_to_video_input(fs, video_data)
    assert input[0] == "-" and input[1] == cfg


def test_array_to_video_input_nodata(image_spec):
    fs = 30
    size, pix_fmt = image_spec
    size_str = f"{size[0]}x{size[1]}"
    codec = "h264"

    cfg = {"c:v": codec, "s:v": size_str, "r:v": fs, "pix_fmt:v": pix_fmt}
    input = utils.array_to_video_input(fs, codec=codec, pix_fmt=pix_fmt, size=size)
    assert input[0] == "-" and input[1] == cfg

    cfg = {"c:v:0": codec, "s:v:0": size_str, "r:v:0": fs, "pix_fmt:v:0": pix_fmt}
    input = utils.array_to_video_input(
        fs, stream_id=0, codec=codec, pix_fmt=pix_fmt, size=size
    )
    assert input[0] == "-" and input[1] == cfg

    cfg["f"] = "rawvideo"
    input = utils.array_to_video_input(
        fs, stream_id=0, codec=codec, pix_fmt=pix_fmt, size=size, format=True
    )
    assert input[0] == "-" and input[1] == cfg

    cfg["f"] = f = "avi"
    input = utils.array_to_video_input(
        fs, stream_id=0, codec=codec, pix_fmt=pix_fmt, size=size, format=f
    )
    assert input[0] == "-" and input[1] == cfg


def test_analyze_video_input():

    assert utils.analyze_video_input(("-", None))[0] == [{}]

    cfgs,always_copy = utils.analyze_video_input(
        (
            "-",
            {
                "c:v": "h264",
                "s:v:0": "1920x1080",
                "s:v:1": "2560x1440",
                "r:v:0": "30000/1001",
                "r:v:1": 60,
                "pix_fmt:v:1": "rgb",
                "pix_fmt:v": "rgba",
            },
        )
    )
    assert cfgs[0] == {
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "frame_rate": "30000/1001",
        "pix_fmt": "rgba",
    }
    assert cfgs[1] == {
        "codec_name": "h264",
        "width": 2560,
        "height": 1440,
        "frame_rate": 60,
        "pix_fmt": "rgb",
    }

