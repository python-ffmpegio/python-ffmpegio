from ffmpegio import audio, probe
import tempfile, re, logging
from os import path
import pytest

from ffmpegio.configure import global_options

logging.basicConfig(level=logging.DEBUG)


def test_create():
    fs = 8000
    x = audio.create(
        "aevalsrc",
        "sin(420*2*PI*t)|cos(430*2*PI*t)",
        c="FC|BC",
        nb_samples=fs,
        sample_rate=fs,
    )
    assert x.shape == (fs, 2)

    # x = audio.create(
    #     "flite",
    #     text="The rainbow is a division of white light into many beautiful colors.",
    #     nb_samples=1024 * 8,
    # )
    # assert x.shape == (1024 * 8, 1)

    x = audio.create("anoisesrc", d=60, c="pink", r=44100, a=0.5)
    print(x.shape, 60 * 44100)
    assert x.shape == (60 * 44100, 1)

    x = audio.create("sine", f=220, b=4, d=5)
    print(x.shape, 5 * 44100)
    assert x.shape == (5 * 44100, 1)


@pytest.mark.skip(reason="takes too long to test")
def test_read_url():
    rid = 1
    url = f"http://www.stimmdatenbank.coli.uni-saarland.de/csl2wav.php4?file={rid}-i_n"
    fs, x = audio.read(url)
    print(fs, x.shape)


def test_read():

    url = "tests/assets/testaudio-1m.mp3"

    T = 0.51111
    fs, x = audio.read(url, duration=T)
    print(fs * T, int(fs * T), x.shape)
    assert int(fs * T) == x.shape[0]

    T = 1.5
    t0 = 0.5
    fs, x1 = audio.read(url, start=t0, end=t0 + T)
    print(int(fs * T), x1.shape)
    assert int(fs * T) == x1.shape[0]


def test_read_write():
    url = "tests/assets/testaudio-1m.mp3"
    outext = ".flac"

    info = probe.audio_streams_basic(
        url, index=0, entries=("sample_rate", "sample_fmt", "channels")
    )[0]

    print(info)

    fs, x = audio.read(url)

    with tempfile.TemporaryDirectory() as tmpdirname:

        print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        print(out_url)
        print(x.shape, x.dtype)
        audio.write(out_url, fs, x)
        fs, y = audio.read(out_url, sample_fmt="flt")
        print(probe.audio_streams_basic(out_url))

        out_url = path.join(tmpdirname, re.sub(r"\..*?$", ".wav", path.basename(url)))
        audio.write(
            out_url,
            fs,
            x,
            codec="pcm_s16le",
            log_level="fatal",
        )
        print(probe.audio_streams_basic(out_url))


if __name__ == "__main__":
    # test_create()
    test_read_write()
