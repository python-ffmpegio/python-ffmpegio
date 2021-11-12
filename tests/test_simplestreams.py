import ffmpegio
import tempfile, re
from os import path
import numpy as np

url = "tests/assets/testmulti-1m.mp4"
outext = ".mp4"


def test_read_write_video():
    # with ffmpegio.open(url, "rv") as f:
    #     F = f.read(-1)
    #     fs = f.frame_rate
    #     print(F.shape)

    fs,F = ffmpegio.video.read(url)

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wv", rate=fs) as f:
            f.write(F[0, ...])
            f.write(F[1:, ...])
            print(f.frames_written)


def test_read_audio():
    with ffmpegio.open(url, "ra") as f:
        x = f.read(1024)
        assert x.shape == (1024, f.channels)
    with ffmpegio.open(url, "ra", start=0.5, end=1.2) as f:
        fs = f.sample_rate
        n = int(fs * (1.2)) - int(fs * (0.5))
        blks = [blk for blk in f.readiter(1024)]
        x = np.concatenate(blks)
        print("# of blks: ", len(blks), x.shape)
        assert x.shape == (n, f.channels)


def test_read_write_audio():
    outext = ".flac"

    with ffmpegio.open(url, "ra") as f:
        F = np.concatenate((f.read(100), f.read(-1)))
        fs = f.sample_rate
        print(F.shape, fs)

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wa", rate=fs) as f:
            f.write(F[:100, ...])
            f.write(F[100:, ...])
            print(f.samples_written)

if __name__=="__main__":
    test_read_write_video()
    # test_read_audio()
