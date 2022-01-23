from distutils.debug import DEBUG
import fractions
import io
from time import sleep
import ffmpegio
import tempfile, re
from os import path
import numpy as np
import logging
from ffmpegio import streams

logging.basicConfig(level=logging.DEBUG)

url = "tests/assets/testmulti-1m.mp4"
outext = ".mp4"


def test_read_video():
    with ffmpegio.open(url, "rv", vf="transpose", pix_fmt="gray") as f:
        F = f.read(10)
        print(f.frame_rate)
        print(F.shape)


def test_read_write_video():
    fs, F = ffmpegio.video.read(url, t=1)

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wv", rate_in=fs) as f:
            f.write(F[0, ...])
            f.write(F[1:, ...])


def test_read_audio(caplog):
    # caplog.set_level(logging.DEBUG)

    fs, x = ffmpegio.audio.read(url)

    with ffmpegio.open(url, "ra", show_log=True, blocksize=1024 ** 2) as f:
        # x = f.read(1024)
        # assert x.shape == (1024, f.ac)
        blks = [blk for blk in f]
        x1 = np.concatenate(blks)
        assert np.array_equal(x, x1)

    n0 = int(0.5 * fs)
    n1 = int(1.2 * fs)
    t0 = n0 / fs
    t1 = n1 / fs

    with ffmpegio.open(
        url, "ra", ss_in=t0, to_in=t1, show_log=True, blocksize=1024 ** 2
    ) as f:
        blks = [blk for blk in f]
        log = f.readlog()

    print(log)

    x2 = np.concatenate(blks)
    #     # print("# of blks: ", len(blks), x1.shape)
    # for i, xi in enumerate(x2):
    #     print(i, xi-x[n0 + i])
    #     assert np.array_equal(xi, x[n0 + i])
    assert x2.shape == (n1 - n0, *f.shape)
    assert np.array_equal(x[n0:n1, :], x2)


def test_read_write_audio():
    outext = ".flac"

    with ffmpegio.open(url, "ra") as f:
        F = np.concatenate((f.read(100), f.read(-1)))
        fs = f.sample_rate
        print(F.shape, fs)

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wa", rate_in=fs, show_log=True) as f:
            f.write(F[:100, ...])
            f.write(F[100:, ...])


def test_video_filter():
    url = "tests/assets/testvideo-1m.mp4"

    fps = 10  # fractions.Fraction(60000,1001)
    out = io.BytesIO()

    with ffmpegio.open(url, "rv", blocksize=30, t=30) as src, ffmpegio.open(
        "scale=200:100", "fv", rate_in=src.frame_rate, rate=fps, show_log=True
    ) as f:

        def process(i, frames):
            print(f"{i} - output {len(frames)} frames ({f.nin},{f.nout})")
            out.write(frames)

        for i, frames in enumerate(src):
            process(i, f.filter(frames))
        assert f.frame_rate_in == src.frame_rate
        assert f.frame_rate == fps
        process("end", f.flush())


def test_audio_filter():
    url = "tests/assets/testaudio-1m.mp3"

    sps = 4000  # fractions.Fraction(60000,1001)
    out = io.BytesIO()

    with streams.SimpleAudioReader(url, blocksize=1024 * 8, t=10, ar=32000) as src:

        samples = src.read(src.blocksize)

        with streams.SimpleAudioFilter(
            "lowpass",
            rate_in=src.sample_rate,
            rate=sps,
            show_log=True,
            # ac=src.channels,
            # dtype=src.dtype,
        ) as f:

            def process(i, samples):
                if len(samples):
                    print(f"{i} - output {len(samples)} samples ({f.nin-f.nout})")
                out.write(samples)

            try:
                process(-1, f.filter(samples))
            except TimeoutError:
                pass
            for i, samples in enumerate(src):
                try:
                    process(i, f.filter(samples))
                except TimeoutError:
                    pass
            assert f.sample_rate_in == src.sample_rate
            assert f.sample_rate == sps
            process("end", f.flush())


if __name__ == "__main__":
    test_audio_filter()

    # python tests\test_simplestreams.py
