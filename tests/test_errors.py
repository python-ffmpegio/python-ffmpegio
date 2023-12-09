from pprint import pprint
import tempfile, re
from os import path
from ffmpegio.ffmpegprocess import run, PIPE
from ffmpegio import FFmpegError, caps, probe
import pytest


def test_errors():
    out = run({"inputs": [], "outputs": [], "global_options": {}}, capture_log=True)
    assert FFmpegError(out.stderr).ffmpeg_msg == "No ffmpeg command argument specified"

    out = run(
        {"inputs": [("fake.avi", None)], "outputs": [], "global_options": {}},
        capture_log=True,
    )
    assert FFmpegError(out.stderr).ffmpeg_msg in (
        "fake.avi: No such file or directory",
        "Error opening input file fake.avi.\n  Error opening input files: No such file or directory",
    )


def test_caps_errors():
    with pytest.raises(FFmpegError):
        caps.bsfilter_info("bogus")
    with pytest.raises(FFmpegError):
        caps.muxer_info("bogus")
    with pytest.raises(FFmpegError):
        caps.demuxer_info("bogus")
    with pytest.raises(FFmpegError):
        caps.encoder_info("bogus")
    with pytest.raises(FFmpegError):
        caps.decoder_info("bogus")
    with pytest.raises(FFmpegError):
        caps.filter_info("bogus")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdirname:
        out = run(
            {
                "inputs": [(url, {}), (srt, None)],
                "outputs": [
                    (
                        out_url,
                        {"vf": "scale=dstw=100", "c:s": "mov_text"},
                    )
                ],
                "global_options": {},
            },
            capture_log=True,
        )

    print(out.stderr)
    if out.returncode:
        raise FFmpegError(out.stderr)
    else:
        print("noerror")  # print(out.returncode)
    # assert str(FFmpegError(out.stderr)) == "Output file #0 does not contain any stream"
