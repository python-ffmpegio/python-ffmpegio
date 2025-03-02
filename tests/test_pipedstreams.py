import logging

logging.basicConfig(level=logging.DEBUG)

from os import path
import pytest
from tempfile import TemporaryDirectory

import ffmpegio as ff
from ffmpegio import streams

mult_url = "tests/assets/testmulti-1m.mp4"
video_url = "tests/assets/testvideo-1m.mp4"
audio_url = "tests/assets/testaudio-1m.mp3"
outext = ".mp4"


def test_PipedMediaReader():
    with streams.PipedMediaReader(mult_url, t=1) as reader:
        # data = reader.read(2)
        for data in reader:
            for k, v in data.items():
                print(f"{k}: {len(v['buffer'])}")


def test_PipedMediaWriter_audio():

    ff.use("read_numpy")

    rates, data = ff.media.read(audio_url, t=1, ar=8000, sample_fmt="s16")
    stream_types = [spec.split(":", 2)[1] for spec in data]

    with streams.PipedMediaWriter(
        "pipe",
        stream_types,
        *rates.values(),
        show_log=True,
        f="matroska",
        # loglevel="debug",
    ) as writer:
        for i, (mtype, frame) in enumerate(zip(stream_types, data.values())):
            writer.write(i, frame)
            writer.write(i, None)

        # close the input and wait for FFmpeg to finish encoding and terminate
        writer.wait(10)

        # read the encoded bytes
        b = writer.pop_encoded()


def test_PipedMediaWriter():

    ff.use("read_numpy")

    rates, data = ff.media.read(mult_url, t=1)
    stream_types = [spec.split(":", 2)[1] for spec in data]

    with streams.PipedMediaWriter(
        "pipe", stream_types, *rates.values(), show_log=True, f="matroska"
    ) as writer:
        for i, (mtype, frame) in enumerate(zip(stream_types, data.values())):
            if mtype == "v":
                writer.write(i, frame[0])
            else:
                writer.write(i, frame)

        writer.wait(10)
        b = writer.pop_encoded(0)
        assert isinstance(b, bytes)
