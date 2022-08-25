import logging

logging.basicConfig(level=logging.DEBUG)

import ffmpegio
import tempfile, re
from os import path
from ffmpegio import streams, utils

url = "tests/assets/testmulti-1m.mp4"
outext = ".mp4"


def test_read_video():
    w = 420
    h = 360
    with ffmpegio.open(
        url, "rv", vf="transpose", pix_fmt="gray", s=(w, h), show_log=True
    ) as f:
        F = f.read(10)
        print(f.rate)
        assert f.shape == (h, w, 1)
        assert f.samplesize == w * h
        assert F["shape"] == (10, h, w, 1)
        assert F["dtype"] == f.dtype


def test_read_write_video():
    fs, F = ffmpegio.video.read(url, t=1)
    bps = utils.get_samplesize(F["shape"][-3:], F["dtype"])
    F0 = {
        "buffer": F["buffer"][:bps],
        "shape": (1, *F["shape"][1:]),
        "dtype": F["dtype"],
    }
    F1 = {
        "buffer": F["buffer"][bps:],
        "shape": (F["shape"][0] - 1, *F["shape"][1:]),
        "dtype": F["dtype"],
    }

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wv", rate_in=fs) as f:
            f.write(F0)
            f.write(F1)


def test_read_audio(caplog):
    # caplog.set_level(logging.DEBUG)

    fs, x = ffmpegio.audio.read(url)
    bps = utils.get_samplesize(x["shape"][-1:], x["dtype"])

    with ffmpegio.open(url, "ra", show_log=True, blocksize=1024 ** 2) as f:
        # x = f.read(1024)
        # assert x['shape'] == (1024, f.ac)
        blks = [blk["buffer"] for blk in f]
    x1 = b"".join(blks)
    assert x["buffer"] == x1

    n0 = int(0.5 * fs)
    n1 = int(1.2 * fs)
    t0 = n0 / fs
    t1 = n1 / fs

    with ffmpegio.open(
        url, "ra", ss_in=t0, to_in=t1, show_log=True, blocksize=1024 ** 2
    ) as f:
        blks, shapes = zip(*[(blk["buffer"], blk["shape"][0]) for blk in f])
        log = f.readlog()
        shape = sum(shapes)

    print(log)

    x2 = b"".join(blks)
    #     # print("# of blks: ", len(blks), x1['shape'])
    # for i, xi in enumerate(x2):
    #     print(i, xi-x[n0 + i])
    #     assert np.array_equal(xi, x[n0 + i])
    assert shape == n1 - n0
    assert x["buffer"][n0 * bps : n1 * bps] == x2


def test_read_write_audio():
    outext = ".flac"

    with ffmpegio.open(url, "ra") as f:
        F = b"".join((f.read(100)["buffer"], f.read(-1)["buffer"]))
        fs = f.rate
        shape = f.shape
        dtype = f.dtype
        bps = f.samplesize

    out = {"dtype": dtype, "shape": shape}

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(out_url, "wa", rate_in=fs, show_log=True) as f:
            f.write({**out, "buffer": F[: 100 * bps]})
            f.write({**out, "buffer": F[100 * bps :]})


def test_video_filter():
    url = "tests/assets/testvideo-1m.mp4"

    fps = 10  # fractions.Fraction(60000,1001)

    with ffmpegio.open(url, "rv", blocksize=30, t=30) as src, ffmpegio.open(
        "scale=200:100", "fv", rate_in=src.rate, rate=fps, show_log=True
    ) as f:

        def process(i, frames):
            print(f"{i} - output {frames['shape'][0]} frames ({f.nin},{f.nout})")

        for i, frames in enumerate(src):
            process(i, f.filter(frames))
        assert f.rate_in == src.rate
        assert f.rate == fps
        process("end", f.flush())


def test_audio_filter():
    url = "tests/assets/testaudio-1m.mp3"

    sps = 4000  # fractions.Fraction(60000,1001)

    with streams.SimpleAudioReader(url, blocksize=1024 * 8, t=10, ar=32000) as src:

        samples = src.read(src.blocksize)

        with streams.SimpleAudioFilter(
            "lowpass",
            rate_in=src.rate,
            rate=sps,
            show_log=True,
            # ac=src.channels,
            # dtype=src['dtype'],
        ) as f:

            def process(i, samples):
                if len(samples):
                    print(
                        f"{i} - output {samples['shape'][0]} samples ({f.nin, f.nout})"
                    )

            try:
                process(-1, f.filter(samples))
            except TimeoutError:
                pass
            for i, samples in enumerate(src):
                try:
                    process(i, f.filter(samples))
                except TimeoutError:
                    pass
            assert f.rate_in == src.rate
            assert f.rate == sps
            process("end", f.flush())


def test_write_extra_inputs():
    url_aud = "tests/assets/testaudio-1m.mp3"

    fs, F = ffmpegio.video.read(url, t=1)
    F = {
        "buffer": F["buffer"],
        "shape": F["shape"],
        "dtype": F["dtype"],
    }

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with ffmpegio.open(
            out_url,
            "wv",
            rate_in=fs,
            extra_inputs=[url_aud],
            map=["0:v", "1:a"],
            show_log=True,
        ) as f:
            f.write(F)

        info = ffmpegio.probe.streams_basic(out_url)
        assert len(info) == 2

        with ffmpegio.open(
            out_url,
            "wv",
            rate_in=fs,
            extra_inputs=[("anoisesrc", {"f": "lavfi"})],
            map=["0:v", "1:a"],
            shortest=None,
            show_log=True,
            overwrite=True,
        ) as f:
            f.write(F)

        info = ffmpegio.probe.streams_basic(out_url)
        assert len(info) == 2


if __name__ == "__main__":
    print("starting test")
    logging.debug("logging check")
    test_video_filter()

    # python tests\test_simplestreams.py
