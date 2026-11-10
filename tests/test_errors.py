import tempfile
from ffmpegio.ffmpegprocess import run
from ffmpegio import FFmpegError, caps
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
