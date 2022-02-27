import tempfile, re
from os import path
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
    assert FFmpegError(out.stderr).ffmpeg_msg == "fake.avi: No such file or directory"

def test_caps_errors():
    with pytest.raises(FFmpegError):
        caps.bsfilter_info('bogus')
    with pytest.raises(FFmpegError):
        caps.muxer_info('bogus')
    with pytest.raises(FFmpegError):
        caps.demuxer_info('bogus')
    with pytest.raises(FFmpegError):
        caps.encoder_info('bogus')
    with pytest.raises(FFmpegError):
        caps.decoder_info('bogus')
    with pytest.raises(FFmpegError):
        caps.filter_info('bogus')
    
if __name__ == "__main__":

    # import os
    # os.environ['FFREPORT']="file=H:\\ffreport.log" 

    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(probe.audio_streams_basic(url))
        url = r"tests\assets\testvideo-1m.mp4"
        # url = r"tests\assets\testaudio-1m.mp3"
        out_url = path.join(tmpdirname, "test.rgb")

        out = run(
            {
                "inputs": [(url, {})], 
                "outputs": [
                    (
                        url,
                        {"vframes": 10},
                    )
                ],
                "global_options": {'y':None},
            },
            capture_log=True,
        )

    print(out.stderr)
    if out.returncode:
        raise FFmpegError(out.stderr)
    else:
        print(out.returncode)
    # assert str(FFmpegError(out.stderr)) == "Output file #0 does not contain any stream"
