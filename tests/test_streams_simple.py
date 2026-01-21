import logging

logging.basicConfig(level=logging.DEBUG)

import re
import tempfile
from os import path

import ffmpegio
from ffmpegio import utils
from ffmpegio.streams import StdFFmpegRunner

url = "tests/assets/testmulti-1m.mp4"
outext = ".mp4"


def test_read_video():
    w = 420
    h = 360
    with StdFFmpegRunner.create_simple_reader(
        [(url, {})],
        {"map": "0:V:0", "vf": "transpose", "pix_fmt": "gray", "s": (w, h), "r": 30},
        show_log=True,
    ) as f:
        F = f.read(10)
        assert f.output_rates[0] == 30
        assert f.output_shapes[0] == (h, w, 1)
        assert F["shape"] == (10, h, w)
        assert F["dtype"] == f.output_dtypes[0]


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
        with StdFFmpegRunner.create_simple_writer("v", {"r": fs}, [(out_url, {})]) as f:
            f.write(F0)
            f.write(F1)
            f.wait()
        fs, F = ffmpegio.video.read(out_url)
        assert len(F["buffer"])


def test_read_audio():
    fs, x = ffmpegio.audio.read(url)
    bps = utils.get_samplesize(x["shape"][-1:], x["dtype"])

    # validate read iterator obtains all the samples
    with StdFFmpegRunner.create_simple_reader(
        [(url, {})], {"map": "0:a:0"}, show_log=True, blocksize=1024**2
    ) as f:
        # x = f.read(1024)
        # assert x['shape'] == (1024, f.ac)
        blks = [blk["buffer"] for blk in f]
    x1 = b"".join(blks)
    assert x["buffer"] == x1

    # validate starting
    n0 = int(0.5 * fs)
    n1 = int(1.2 * fs)
    t0 = n0 / fs
    t1 = n1 / fs

    with StdFFmpegRunner.create_simple_reader(
        [(url, {})],
        {"map": "0:a:0"},
        show_log=True,
        blocksize=1024**2,
        ss_in=t0,
        to_in=t1,
    ) as f:
        blks, shapes = zip(*[(blk["buffer"], blk["shape"][0]) for blk in f])
        shape = sum(shapes)

    x2 = b"".join(blks)
    #     # print("# of blks: ", len(blks), x1['shape'])
    # for i, xi in enumerate(x2):
    #     print(i, xi-x[n0 + i])
    #     assert np.array_equal(xi, x[n0 + i])
    assert shape == n1 - n0
    assert x["buffer"][n0 * bps : n1 * bps] == x2


def test_read_write_audio():
    outext = ".flac"

    with StdFFmpegRunner.create_simple_reader([(url, {})], {"map": "0:a:0"}) as f:
        F = b"".join((f.read(100)["buffer"], f.read(-1)["buffer"]))
        fs = f.output_rates[0]
        shape = f.output_shapes[0]
        dtype = f.output_dtypes[0]
        bps = f.output_itemsizes[0]

    out = {"dtype": dtype, "shape": shape}

    print(len(F[: 100 * bps]))

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with StdFFmpegRunner.create_simple_writer(
            "a", {"ar": fs}, [(out_url, {})], show_log=True
        ) as f:
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
    print(len(F["buffer"]))

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        with StdFFmpegRunner.create_simple_writer(
            "v",
            {"r": fs},
            [(out_url, {})],
            extra_inputs=[(url_aud, {})],
            show_log=True,
            **{"map": ["0:v", "1:a"], "loglevel": "debug"},
        ) as f:
            f.write(F)
            f.wait()
            print(f.readlog())

        info = ffmpegio.probe.streams_basic(out_url)
        assert len(info) == 2

        with StdFFmpegRunner.create_simple_writer(
            "v",
            {"r": fs},
            [(out_url, {})],
            extra_inputs=[("anoisesrc", {"f": "lavfi"})],
            show_log=True,
            overwrite=True,
            **{"map": ["0:v", "1:a"], "shortest": None},
        ) as f:
            f.write(F)
            f.wait()
            print(f.readlog())

        info = ffmpegio.probe.streams_basic(out_url)
        assert len(info) == 2
