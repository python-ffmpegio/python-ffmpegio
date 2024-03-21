import logging
from ffmpegio import probe, configure, ffmpegprocess, utils

# logging.basicConfig(level=logging.DEBUG)


def test_run_help():
    ffmpegprocess.run({"global_options": {"help": None}})


def test_run_from_stream():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, container = utils.get_audio_codec(sample_fmt)

    with open(url, "rb") as f:
        args = {
            "inputs": [("-", {"f": "mp3"})],
            "outputs": [
                ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
            ],
        }
        out = ffmpegprocess.run(args, capture_log=True, stdin=f)

    print(f"FFmpeg output: {len(out.stdout)} bytes")
    print(out.stderr)


def test_run_bidir():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, container = utils.get_audio_codec(sample_fmt)

    with open(url, "rb") as f:
        bytes = f.read()  # byte array

    args = {
        "inputs": [("-", {"f": "mp3"})],
        "outputs": [
            ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
        ],
    }

    out = ffmpegprocess.run(args, input=bytes, capture_log=True)

    print(f"FFmpeg output: {len(out.stdout)} bytes")
    print(out.stderr)


def test_run_progress():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, container = utils.get_audio_codec(sample_fmt)

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

        ffmpegprocess.run(args, capture_log=True, progress=progress, stdin=f)


def test_popen():
    url = "tests/assets/testaudio-1m.mp3"
    sample_fmt = "s16"
    out_codec, container = utils.get_audio_codec(sample_fmt)

    with open(url, "rb") as f:
        args = {
            "inputs": [("-", {"f": "mp3"})],
            "outputs": [
                ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})
            ],
        }

        proc = ffmpegprocess.Popen(args, capture_log=True, stdin=f)
        x = proc.stdout.read()
        if proc.wait(50) is None:
            print("ffmpeg not stopping")
            proc.kill()

    print(f"FFmpeg output: {len(x)} samples")


def test_popen_progress():
    url = "tests/assets/testvideo-1m.mp4"
    info = probe.video_streams_basic(
        url, 0, ["pix_fmt", "width", "height", "frame_rate"]
    )
    pix_fmt_in = info["pix_fmt"]
    s_in = (info["width"], info["height"])
    r_in = info["frame_rate"]

    i = 0

    def progress(*args):
        global i
        i += 1
        print(i, args)
        return i > 0

    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url)
    configure.add_url(ffmpeg_args, "output", "-")

    dtype, shape, r = configure.finalize_video_read_opts(
        ffmpeg_args, pix_fmt_in, s_in, r_in
    )

    samplesize = utils.get_samplesize(shape, dtype)

    with ffmpegprocess.Popen(
        ffmpeg_args,
        capture_log=True,
        progress=progress,
    ) as proc:
        for k in range(15):
            print(proc.stderr.readline())
        for j in range(10):
            out = proc.stdout.read(samplesize)
            assert len(out) == samplesize


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
