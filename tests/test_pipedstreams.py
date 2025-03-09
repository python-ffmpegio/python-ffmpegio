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
            writer.write_stream(i, frame)

        # close the input and wait for FFmpeg to finish encoding and terminate
        writer.wait(10)

        # read the encoded bytes
        b = writer.readall_encoded()


def test_PipedMediaWriter():

    ff.use("read_numpy")

    rates, data = ff.media.read(mult_url, t=1)
    stream_types = [spec.split(":", 2)[1] for spec in data]

    with streams.PipedMediaWriter(
        "pipe", stream_types, *rates.values(), show_log=True, f="matroska"
    ) as writer:
        for i, (mtype, frame) in enumerate(zip(stream_types, data.values())):
            if mtype == "v":
                writer.write_stream(i, frame[0])
            else:
                writer.write_stream(i, frame)

        writer.wait(10)
        b = writer.read_encoded_stream(0, -1, 10)
        assert isinstance(b, bytes) and len(b) > 0


def test_PipedMediaFilter():

    ff.use("read_bytes")

    fs, x = ff.audio.read("tests/assets/testaudio-1m.mp3", to=1)

    fps, F = ff.video.read("tests/assets/testvideo-1m.mp4", to=1)

    print(f"video: {len(F['buffer'])} bytes | audio: {len(x['buffer'])} bytes")

    with streams.PipedMediaFilter(
        ["[0:V:0][1:V:0]vstack,split", "[2:a:0][3:a:0]amerge"],
        "vvaa",
        fps,
        fps,
        fs,
        fs,
        output_options={"[out0]": {}, "audio": {"map": "[out2]"}},
        show_log=True,
        loglevel="debug",
        # queuesize=4,
    ) as f:
        # f.write([F, F])
        f.write([F, F, x, x])
        # sleep(1)
        f.wait(10)
        data = f.read(F["shape"][0], 10)

        assert all(k in ("[out0]", "out1", "audio") for k in data)
        n = f.output_counts
        assert all(v["shape"][0] == n[k] for k, v in data.items())


def test_PipedMediaTranscoder():
    url = "tests/assets/testmulti-1m.mp4"

    with streams.PipedMediaTranscoder(
        [],
        [{"f": "matroska", "codec": "copy", "to": 1}],
        extra_inputs=[url],
        show_log=False,
    ) as f:
        if f.wait(timeout=10):
            raise f.lasterror
        data = f.read_encoded_stream(0, -1, timeout=10)

    with streams.PipedMediaTranscoder(
        [{"f": "matroska"}],
        [{"f": "flac"}, {"f": "matroska", "codec": "copy"}],
        show_log=False,
    ) as f:
        f.write_encoded_stream(0, data, timeout=10)
        if f.wait(timeout=10):
            raise f.lasterror
        enc_data = f.readall_encoded(timeout=10)
        assert len(enc_data) == 2
