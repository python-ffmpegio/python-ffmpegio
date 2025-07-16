import logging

logging.basicConfig(level=logging.DEBUG)

import ffmpegio as ff
import tempfile, re
from os import path
from ffmpegio import streams, utils

url = "tests/assets/testmulti-1m.mp4"
outext = ".mp4"


def test_read_video():
    w = 420
    h = 360
    b = ff.transcode(url, "-", f="matroska", c="copy", to=1)
    with (
        streams.StdVideoDecoder(
            vf="transpose", pix_fmt="gray", s=(w, h), show_log=True
        ) as f,
    ):
        f.write_encoded(b)
        F = f.read(10)
        print(f.output_rate)
        assert f.output_shape == (h, w, 1)
        assert f.output_samplesize == w * h
        assert F["shape"] == (10, h, w, 1)
        assert F["dtype"] == f.output_dtype


def test_read_write_video():
    fs, F = ff.video.read(url, t=1)
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

    with streams.StdVideoEncoder(fs, f="matroska", show_log=True) as f:
        f.write(F0)
        f.write(F1)
        f.wait()
        b = f.read_encoded(-1)


def test_read_audio(caplog):
    # caplog.set_level(logging.DEBUG)

    b = ff.transcode(url, "-", f="matroska", c="copy", vn=None)
    fs, x = ff.audio.read(b, to=10, show_log=True, sample_fmt="flt")
    bps = utils.get_samplesize(x["shape"][-1:], x["dtype"])
    with streams.StdAudioDecoder(show_log=True, blocksize=1024**2, to=10) as f:
        f.write_encoded(b)
        # x = f.read(1024)
        # assert x['shape'] == (1024, f.ac)
        blks = [blk["buffer"] for blk in f]
    x1 = b"".join(blks)
    assert x["buffer"] == x1


def test_read_write_audio():
    outext = ".flac"
    b = ff.transcode(url, "-", f="matroska", c="copy", vn=None)

    with streams.StdAudioDecoder(show_log=True, to=10) as f:
        f.write_encoded(b)
        F = b"".join((f.read(100)["buffer"], f.read(-1)["buffer"]))
        fs = f.output_rate
        shape = f.output_shape
        dtype = f.output_dtype
        bps = f.output_samplesize

    out = {"dtype": dtype, "shape": shape}

    with streams.StdAudioEncoder(fs, show_log=True, f="matroska") as f:
        f.write({**out, "buffer": F[: 100 * bps]})
        f.write({**out, "buffer": F[100 * bps :]})


def test_video_filter():
    url = "tests/assets/testvideo-1m.mp4"

    fps = 10  # fractions.Fraction(60000,1001)

    with (
        streams.SimpleVideoReader(url, blocksize=30, t=30) as src,
        streams.StdVideoFilter("scale=200:100", src.output_rate, r=fps, show_log=True) as f,
    ):

        def process(i, frames):
            print(
                f"{i} - output {frames['shape'][0]} frames ({f.input_count},{f.output_count})"
            )

        for i, frames in enumerate(src):
            process(i, f.filter(frames))
        assert f.input_rate == src.output_rate
        assert f.output_rate == fps
        f.wait()
        process("end", f.read(-1))


def test_audio_filter():
    url = "tests/assets/testaudio-1m.mp3"

    sps = 4000  # fractions.Fraction(60000,1001)

    with (
        streams.SimpleAudioReader(url, blocksize=1024 * 8, t=10, ar=32000) as src,
        streams.StdAudioFilter("lowpass", src.output_rate, ar=sps, show_log=True) as f,
    ):
        samples = src.read(src.blocksize)

        def process(i, samples):
            if len(samples):
                print(
                    f"{i} - output {samples['shape'][0]} samples ({f.input_count, f.output_count})"
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
        assert f.input_rate == src.output_rate
        assert f.output_rate == sps
        f.wait()
        process("end", f.read(-1))


def test_write_extra_inputs():
    url_aud = "tests/assets/testaudio-1m.mp3"

    fs, F = ff.video.read(url, t=1)
    F = {
        "buffer": F["buffer"],
        "shape": F["shape"],
        "dtype": F["dtype"],
    }

    with streams.StdVideoEncoder(
        fs,
        extra_inputs=[url_aud],
        f="matroska",
        map=["0:v", "1:a"],
        show_log=True,
    ) as f:
        f.write(F)
        f.wait()
        b = f.read_encoded(-1)

        info = ff.probe.streams_basic(b)
        assert len(info) == 2

        with streams.StdVideoEncoder(
            fs,
            extra_inputs=[("anoisesrc", {"f": "lavfi"})],
            f="matroska",
            map=["0:v", "1:a"],
            shortest=None,
            show_log=True,
        ) as f:
            f.write(F)
            f.wait()
            b = f.read_encoded(-1)

    info = ff.probe.streams_basic(b)
    assert len(info) == 2


if __name__ == "__main__":
    print("starting test")
    logging.debug("logging check")
    test_video_filter()

    # python tests\test_simplestreams.py
