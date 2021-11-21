import ffmpegio
import tempfile, re
from os import path
import numpy as np
import logging

logging.basicConfig(level=logging.DEBUG)

url = "tests/assets/testmulti-1m.mp4"
outext = ".mp4"


def test_read_write_video():
    # with ffmpegio.open(url, "rv") as f:
    #     F = f.read(-1)
    #     fs = f.frame_rate
    #     print(F.shape)

    fs, F = ffmpegio.video.read(url)

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wv", rate=fs) as f:
            f.write(F[0, ...])
            f.write(F[1:, ...])
            print(f.frames_written)


def test_read_audio(caplog):
    caplog.set_level(logging.DEBUG)

    fs, x = ffmpegio.audio.read(url)

    with ffmpegio.open(url, "ra") as f:
        # x = f.read(1024)
        # assert x.shape == (1024, f.channels)
        blks = [blk for blk in f.readiter(1024)]
        x1 = np.concatenate(blks)
        assert np.array_equal(x, x1)

    with ffmpegio.open(url, "ra", start=0.5, end=1.2) as f:
        #     fs = f.sample_rate
        n0 = int(0.5 * fs)
        n1 = int(1.2 * fs)
        #     n = int(fs * (1.2)) - int(fs * (0.5))
        blks = [blk for blk in f.readiter(1024)]
        x2 = np.concatenate(blks)
        #     # print("# of blks: ", len(blks), x1.shape)
        assert np.array_equal(x[n0:n1,:],x2)
        #     assert x1.shape == (n, f.channels)


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


if __name__ == "__main__":
    test_read_write_video()
    # test_read_audio()
