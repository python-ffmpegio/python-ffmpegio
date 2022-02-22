from ffmpegio import ffmpegprocess
from ffmpegio.utils import avi as aviutils
import io
from pprint import pprint

import pytest


@pytest.fixture(
    scope="module",
    params=(
        ("gray", "s32"),  # 1
        ("gray16le", "flt"),  # 2
        ("ya8", "s64"),  # 2
        ("rgb24", "u8"),  # 3
        ("rgba", "s16"),  # 4
        ("grayf32le", "s16"),  # 4
        ("ya16le", "s16"),  # 4
        ("rgb48le", "dbl"),  # 6
        ("rgba64le", "s16"),  # 8
    ),
)
def avi_stream(request):
    url = "tests/assets/testmulti-1m.mp4"
    codecs = dict(
        u8="pcm_u8",
        s16="pcm_s16le",
        s32="pcm_s32le",
        s64="pcm_s64le",
        flt="pcm_f32le",
        dbl="pcm_f64le",
    )
    vframes = 16
    f = io.BytesIO(
        ffmpegprocess.run(
            {
                "inputs": [(url, None)],
                "outputs": [
                    (
                        "-",
                        {
                            "f": "avi",
                            "vcodec": "rawvideo",
                            "pix_fmt": request.param[0],
                            "acodec": codecs[request.param[1]],
                            "vframes": vframes,
                        },
                    )
                ],
            }
        ).stdout
    )
    return [f, vframes, *request.param]


def test_base_func(avi_stream):
    f, vframes, pix_fmt, sample_fmt = avi_stream
    f.seek(0)

    streams = aviutils.read_header(f, pix_fmt.startswith("ya"))[0]
    assert streams[0]["pix_fmt"] == pix_fmt
    assert streams[1]["sample_fmt"] == sample_fmt

    i = 0
    while True:
        try:
            sid, data = aviutils.read_frame(f)
        except:
            break
        if sid == 0:
            i += 1
    assert i == vframes


def test_avireader(avi_stream):
    f, vframes, pix_fmt, sample_fmt = avi_stream
    f.seek(0)
    reader = aviutils.AviReader()
    reader.start(f, pix_fmt.startswith("ya"))
    streams = reader.streams
    i = 0
    for id, frame in reader:
        if id == 0:
            i += 1

    assert i == vframes


if __name__ == "__main__":
    url = "tests/assets/testmulti-1m.mp4"
    url1 = "tests/assets/testvideo-1m.mp4"
    url2 = "tests/assets/testaudio-1m.mp3"

    # 3840 × 2160 x 3
    # with AviStreams.AviMediaReader(
    #     url1, url2, t=1, blocksize=1000, ref_stream="a:0"
    # ) as reader:
    #     for data in reader:
    #         print({k: (v.shape, v.dtype) for k, v in data.items()})

    # create a short example with both audio & video
    f = io.BytesIO(
        ffmpegprocess.run(
            {
                "inputs": [(url1, None), (url2, None)],
                "outputs": [
                    (
                        "-",
                        {
                            "f": "avi",
                            "vcodec": "rawvideo",
                            "pix_fmt": "rgb24",
                            "acodec": "pcm_s16le",
                            "vframes": 16,
                        },
                    )
                ],
            }
        ).stdout
    )

    streams, hdrl = aviutils.read_header(f)
    pprint(streams[0]["pix_fmt"])
    pprint(streams[1]["sample_fmt"])
    pprint(hdrl)
    i = 0
    while True:
        try:
            sid, data = aviutils.read_frame(f)
        except:
            break
        print(sid, len(data))
        if sid == 0:
            i += 1

    print(f"read {i} frames")
