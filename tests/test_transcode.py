from ffmpegio import transcode, probe, FFmpegError
import tempfile, re
from os import path


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
        try:
            transcode(url, out_url, overwrite=False)
            raise RuntimeError("failed to abort unforced output-file-exist case")
        except FFmpegError:
            pass
        transcode(url, out_url, overwrite=True, show_log=True, progress=progress)

        # with open(path.join(tmpdirname, "progress.txt")) as f:
        #     print(f.read())


def test_transcode_vf():
    url = "tests/assets/testmulti-1m.mp4"
    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, path.basename(url))
        transcode(url, out_url, t='0.1', vf="scale=in_w:in_h*9/10", show_log=True)
        assert path.isfile(out_url)


if __name__ == "__main__":
    test_transcode()
