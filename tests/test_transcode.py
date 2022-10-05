from ffmpegio import transcode, probe, FFmpegError, FilterGraph
import tempfile, re
from os import path
import pytest


def test_transcode():
    url = "tests/assets/testmulti-1m.mp4"
    outext = ".flac"

    progress = lambda d, done: print(d, done)

    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        # print(out_url)
        transcode(url, out_url, overwrite=True)
        # print(probe.audio_streams_basic(out_url))
        # transcode(url, out_url)
        with pytest.raises(FFmpegError):
            transcode(url, out_url, overwrite=False)
        transcode(url, out_url, overwrite=True, show_log=True, progress=progress)

        # test mimo
        url1 = "tests/assets/testvideo-1m.mp4"
        out_url1 = path.join(tmpdirname, "vid1.mp4")
        out_url2 = path.join(tmpdirname, "vid2.mp4")
        transcode(
            [url, url1],
            [(out_url1, {"map": "1:v:0"}), (out_url2, {"map": "0:v:0"})],
            vframes=10,
        )


def test_transcode_from_filter():
    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, "test.png")
        transcode("color=r=1:d=1", out_url, f_in="lavfi", vframes=1, show_log=True)
        transcode(
            FilterGraph([[("color", {"r": 1, "d": 1})]]),
            out_url,
            f_in="lavfi",
            vframes=1,
            show_log=True,
            overwrite=True,
        )
        transcode(
            FilterGraph([[("color", {"r": 1, "d": 1})]]),
            out_url,
            f_in="lavfi",
            pix_fmt="rgba",
            vframes=1,
            show_log=True,
            overwrite=True,
        )


def test_transcode_2pass():
    url = "tests/assets/testmulti-1m.mp4"

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, path.basename(url))
        transcode(
            url,
            out_url,
            show_log=True,
            two_pass=True,
            t=1,
            **{"c:v": "libx264", "b:v": "1000k", "c:a": "aac", "b:a": "128k"}
        )

        transcode(
            url,
            out_url,
            show_log=True,
            two_pass=True,
            pass1_omits=["c:a", "b:a"],
            pass1_extras={"an": None},
            overwrite=True,
            t=1,
            **{"c:v": "libx264", "b:v": "1000k", "c:a": "aac", "b:a": "128k"}
        )


def test_transcode_vf():
    url = "tests/assets/testmulti-1m.mp4"
    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, path.basename(url))
        transcode(url, out_url, t="0.1", vf="scale=in_w:in_h*9/10", show_log=True)
        assert path.isfile(out_url)


def test_transcode_image():
    url = "tests/assets/ffmpeg-logo.png"
    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, path.basename(url) + ".jpg")
        transcode(
            url,
            out_url,
            show_log=True,
            remove_alpha=True,
            s=[300, -1],
            transpose=0,
            vframes=1,
        )


if __name__ == "__main__":
    test_transcode_from_filter()
