import logging
import re
import tempfile
from os import path

import numpy as np
import pytest

from ffmpegio import audio, probe
from ffmpegio import filtergraph as fgb

logging.basicConfig(level=logging.DEBUG)


def test_create():
    fs = 8000
    fs, x = audio.create(
        "aevalsrc",
        "sin(420*2*PI*t)|cos(430*2*PI*t)",
        d=1,
        nb_samples=fs,
        sample_rate=fs,
        show_log=True,
    )
    assert x["shape"] == (fs, 2)

    # x = audio.create(
    #     "flite",
    #     text="The rainbow is a division of white light into many beautiful colors.",
    #     nb_samples=1024 * 8,
    # )
    # assert x['shape'] == (1024 * 8, 1)

    fs, x = audio.create("anoisesrc", d=60, c="pink", r=44100, a=0.5)
    print(x["shape"], 60 * 44100)
    assert x["shape"] == (60 * 44100,)

    fs, x = audio.create("sine", f=220, b=4, d=5)
    print(x["shape"], 5 * 44100)
    assert x["shape"] == (5 * 44100,)


@pytest.mark.skip(reason="takes too long to test")
def test_read_url():
    rid = 1
    url = f"http://www.stimmdatenbank.coli.uni-saarland.de/csl2wav.php4?file={rid}-i_n"
    fs, x = audio.read(url)
    print(fs, x["shape"])


def test_read():

    url = "tests/assets/testaudio-1m.mp3"

    T = 0.51111
    T = 0.49805
    fs, x = audio.read(url, t=T, show_log=True)
    print(fs * T, round(fs * T), x["shape"])
    assert round(fs * T) == x["shape"][0]

    T = 1.5
    t0 = 0.5
    fs, x1 = audio.read(url, ss=t0, to=t0 + T)
    print(int(fs * T), x1["shape"])
    assert round(fs * T) == x1["shape"][0]

    # n0 = int(t0 * fs)
    # N = int(T * fs)

    # fs, x2 = audio.read(url, ss=n0, t=N, units="samples")
    # assert x1['shape'] == x2.shape
    # assert np.array_equal(x1, x2)


def test_read_af():

    url = "tests/assets/testaudio-1m.mp3"

    T = 0.51111
    T = 0.49805
    fs, x = audio.read(
        url, t=T, show_log=True, af="aresample=8000,channelmap=map=FL-FC"
    )
    assert fs == 8000
    assert len(x["shape"]) == 1


def test_read_filter():

    url = "tests/assets/testaudio-1m.mp3"

    T = 0.51111
    T = 0.49805
    fs, x = audio.read(
        [url, url],
        t=T,
        show_log=True,
        filter_complex="[0][1]amix[mixed]",
        map="[mixed]",
    )


def test_read_write():
    url = "tests/assets/testaudio-1m.mp3"
    outext = ".flac"

    fs, x = audio.read(url)

    with tempfile.TemporaryDirectory() as tmpdirname:
        print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        print(out_url)
        print(x["shape"], x["dtype"])
        audio.write(out_url, fs, x)
        fs, y = audio.read(out_url, sample_fmt="flt")
        print(probe.audio_streams_basic(out_url))

        out_url = path.join(tmpdirname, re.sub(r"\..*?$", ".wav", path.basename(url)))
        audio.write(out_url, fs, x, acodec="pcm_s16le", loglevel="fatal", show_log=True)
        print(probe.audio_streams_basic(out_url))


def test_filter():
    input_rate = 44100
    input = {
        "buffer": b"\xef" * input_rate * 2,
        "dtype": "<i2",
        "shape": (input_rate, 1),
    }
    expr = fgb.Graph(
        [
            [
                fgb.channelmap(channel_layout="stereo", map="FC|FC"),
                fgb.bandpass(channels="FL"),
                fgb.aresample(22050),
            ]
        ],
    )

    output_rate, output = audio.filter(
        expr, input_rate, input, show_log=True, loglevel="verbose"
    )
    assert output_rate == 22050
    assert output["shape"] == (22050, 2)
    assert output["dtype"] == input["dtype"]

    # force output format and rate
    output_rate, output = audio.filter(
        expr, input_rate, input, ar=44100, sample_fmt="s16"
    )
    assert output_rate == 44100
    assert output["shape"] == (44100, 2)
    assert output["dtype"] == "<i2"

    # complex filtergraph
    expr = fgb.Graph(
        [[fgb.anoisesrc(44100, color="pink"), fgb.amerge()]],
        {"in": [(0, 1, 0), None], "out": [None, (0, 1, 0)]},
    )
    output_rate, output = audio.filter(expr, input_rate, input)
    assert output_rate == 44100
    assert output["shape"] == (44100, 2)
    assert output["dtype"] == "<i2"

    output_rate, output = audio.filter("[in]bandpass[out]", input_rate, input)


def test_read_buffin():

    url = "tests/assets/testaudio-1m.mp3"

    T = 0.49805

    with open(url, "rb") as f:
        b = f.read()

    fs, x = audio.read(b, t=T, show_log=True)
    assert round(fs * T) == x["shape"][0]


def test_read_fileobj():

    url = "tests/assets/testaudio-1m.mp3"

    T = 0.49805

    with open(url, "rb") as f:
        fs, x = audio.read(f, t=T, show_log=True)
        assert round(fs * T) == x["shape"][0]


def test_write_buffout():

    fs = 16000
    x = np.random.randint(-(2**15), 2**15, fs, np.int16)
    out = audio.write("-", fs, x, f="flv", acodec="aac", show_log=True)
    assert len(out) > 0


def test_write_fileobj():

    fs = 16000
    x = np.random.randint(-(2**15), 2**15, fs, np.int16)
    with tempfile.TemporaryDirectory() as tmpdirname:
        url = path.join(tmpdirname, "test.flv")
        with open(url, "wb") as f:
            audio.write(f, fs, x, f="flv", acodec="aac", show_log=True)


def test_filter_empty():
    fs, y = audio.filter(
        "aresample=8000,pan=mono|c0=c0", 44100, np.empty((0, 2)), squeeze=False
    )
    assert fs == 8000
    assert y["shape"] == (0, 1)
