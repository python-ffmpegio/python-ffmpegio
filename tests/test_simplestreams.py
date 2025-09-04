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
    with streams.SimpleVideoReader(
        url, vf="transpose", pix_fmt="gray", s=(w, h), show_log=True, r=30
    ) as f:
        F = f.read(10)
        assert f.output_rate == 30
        assert f.output_shape == (h, w, 1)
        assert F["shape"] == (10, h, w, 1)
        assert F["dtype"] == f.output_dtype


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
        with streams.SimpleVideoWriter(out_url, fs) as f:
            f.write(F0)
            f.write(F1)
            f.wait()
        fs, F = ffmpegio.video.read(out_url)
        assert len(F['buffer'])


def test_read_audio(caplog):
    # caplog.set_level(logging.DEBUG)

    fs, x = ffmpegio.audio.read(url)
    bps = utils.get_samplesize(x["shape"][-1:], x["dtype"])

    with streams.SimpleAudioReader(url, show_log=True, blocksize=1024**2) as f:
        # x = f.read(1024)
        # assert x['shape'] == (1024, f.ac)
        blks = [blk["buffer"] for blk in f]
    x1 = b"".join(blks)
    assert x["buffer"] == x1

    n0 = int(0.5 * fs)
    n1 = int(1.2 * fs)
    t0 = n0 / fs
    t1 = n1 / fs

    with streams.SimpleAudioReader(
        url, ss_in=t0, to_in=t1, show_log=True, blocksize=1024**2
    ) as f:
        blks, shapes = zip(*[(blk["buffer"], blk["shape"][0]) for blk in f])
        log = f.readlog(-1)
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

    with streams.SimpleAudioReader(url) as f:
        F = b"".join((f.read(100)["buffer"], f.read(-1)["buffer"]))
        fs = f.output_rate
        shape = f.output_shape
        dtype = f.output_dtype
        bps = f.output_bytesize

    out = {"dtype": dtype, "shape": shape}

    print(len(F[: 100 * bps]))

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with streams.SimpleAudioWriter(out_url, fs, show_log=True) as f:
            f.write({**out, "buffer": F[: 100 * bps]})
            f.write({**out, "buffer": F[100 * bps :]})
            f.wait()
        assert path.exists(out_url)


def test_write_extra_inputs():
    url_aud = "tests/assets/testaudio-1m.mp3"

    fs, F = ffmpegio.video.read(url, t=1)
    F = {
        "buffer": F["buffer"],
        "shape": F["shape"],
        "dtype": F["dtype"],
    }
    print(len(F['buffer']))

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with streams.SimpleVideoWriter(
            out_url, fs, extra_inputs=[url_aud], map=["0:v", "1:a"], show_log=True,loglevel='debug'
        ) as f:
            f.write(F)
            f.wait()
            print(f.readlog())

        info = ffmpegio.probe.streams_basic(out_url)
        assert len(info) == 2

        with streams.SimpleVideoWriter(
            out_url,
            fs,
            extra_inputs=[("anoisesrc", {"f": "lavfi"})],
            map=["0:v", "1:a"],
            shortest=None,
            show_log=True,
            overwrite=True,
        ) as f:
            f.write(F)
            f.wait()
            print(f.readlog())

        info = ffmpegio.probe.streams_basic(out_url)
        assert len(info) == 2
