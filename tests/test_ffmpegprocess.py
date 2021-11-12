import pytest

from ffmpegio import ffmpegprocess
from ffmpegio import utils

# logging.basicConfig(level=logging.DEBUG)


def test_run_help():
    ffmpegprocess.run("-help")


def test_run_from_stream():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, dtype = utils.get_audio_format(sample_fmt)
    container = out_codec[4:]

    with open(url, "rb") as f:
        args = {
            "inputs": [("-", {"f": "mp3"})],
            "outputs": [
                ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
            ],
        }
        out = ffmpegprocess.run(args, dtype=dtype, capture_log=True, stdin=f)
        x = out.stdout

    print(f"FFmpeg output: {x.size} samples")
    print(out.stderr)


def test_run_bidir():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, dtype = utils.get_audio_format(sample_fmt)
    container = out_codec[4:]

    with open(url, "rb") as f:
        bytes = f.read()  # byte array

    args = {
        "inputs": [("-", {"f": "mp3"})],
        "outputs": [
            ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
        ],
    }

    out = ffmpegprocess.run(args, input=bytes, dtype=dtype, capture_log=True)
    x = out.stdout

    print(f"FFmpeg output: {x.size} samples")
    print(out.stderr)


def test_progress():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, dtype = utils.get_audio_format(sample_fmt)
    container = out_codec[4:]

    def progress(*args):
        print(args)
        return False

    with open(url, "rb") as f:
        args = {
            "inputs": [("-", {"f": "mp3"})],
            "outputs": [
                ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
            ],
        }

        ffmpegprocess.run(
            args, dtype=dtype, capture_log=True, progress=progress, stdin=f
        )


def test_popen():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, dtype = utils.get_audio_format(sample_fmt)
    container = out_codec[4:]

    with open(url, "rb") as f:
        args = {
            "inputs": [("-", {"f": "mp3"})],
            "outputs": [
                ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
            ],
        }

        proc = ffmpegprocess.Popen(args, dtype=dtype, capture_log=True, stdin=f)
        x = proc.stdout.read_as_array(100, block=True, dtype=dtype)
        if proc.wait(50) is None:
            print("ffmpeg not stopping")
            proc.kill()

    print(f"FFmpeg output: {len(x)} samples")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    test_run_bidir()