from ffmpegio import utils, caps
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
    assert cfg[0] == "rgb24" and cfg[1] == 3 and cfg[2] == np.uint8


def test_get_rotated_shape():
    w = 1000
    h = 400
    print(utils.get_rotated_shape(w, h, 30))
    print(utils.get_rotated_shape(w, h, 45))
    print(utils.get_rotated_shape(w, h, 60))
    assert utils.get_rotated_shape(w, h, 90) == (h, w, np.pi / 2.0)


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

    cfg = {"f": "s16le", "c:a": "pcm_s16le", "ac": 1, "ar": 44100, "sample_fmt": "s16"}
    input = utils.array_to_audio_input(fs, sample)[0]
    assert input[0] == "-" and input[1] == cfg

    cfg = {"f": "s16le", "c:a": "pcm_s16le", "ac": 4, "ar": 44100, "sample_fmt": "s16"}
    input = utils.array_to_audio_input(fs, data)[0]
    assert input[0] == "-" and input[1] == cfg

    cfg = {
        "f": "s16le",
        "c:a:0": "pcm_s16le",
        "ac:a:0": 4,
        "ar:a:0": 44100,
        "sample_fmt:a:0": "s16",
    }
    input = utils.array_to_audio_input(fs, data, 0)[0]
    assert input[0] == "-" and input[1] == cfg

    cfg = {
        "f": "s16le",
        "c:a:1": "pcm_s16le",
        "ac:a:1": 4,
        "ar:a:1": 44100,
        "sample_fmt:a:1": "s16",
    }
    input = utils.array_to_audio_input(fs, data, 1)[0]
    assert input[0] == "-" and input[1] == cfg

    cfg = {
        "f": "s16le",
        "c:a:1": "pcm_s16le",
        "ac:a:1": 4,
        "ar:a:1": 44100,
        "sample_fmt:a:1": "s16",
    }
    with pytest.raises(Exception):
        # no sample_fmt or channels
        input = utils.array_to_audio_input(fs, 1)


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

    cfg = {
        "f": "rawvideo",
        "c:v": "rawvideo",
        "s": size,
        "r": fs,
        "pix_fmt": pix_fmt,
    }

    input = utils.array_to_video_input(fs, video_data)
    assert input[0] == "-" and input[1] == cfg


def test_array_to_video_input_nodata(image_spec):
    fs = 30
    size, pix_fmt = image_spec

    dtype, ncomp, _ = utils.get_video_format(pix_fmt)
    shape = (*size[::-1], ncomp)

    cfg = {"f": "rawvideo", "c:v": "rawvideo", "s": size, "r": fs, "pix_fmt": pix_fmt}
    input = utils.array_to_video_input(fs, dtype=dtype, shape=shape)
    assert input[0] == "-" and input[1] == cfg

    cfg = {
        "f": "rawvideo",
        "c:v:0": "rawvideo",
        "s:v:0": size,
        "r:v:0": fs,
        "pix_fmt:v:0": pix_fmt,
    }
    input = utils.array_to_video_input(fs, stream_id=0, dtype=dtype, shape=shape)
    assert input[0] == "-" and input[1] == cfg


if __name__ == "__main__":
    import re

    spec = "p:4"
    print(re.split(r"(?<![pi]\:|m\:.+?\:)\:", spec))
