import logging

import numpy as np

import ffmpegio as ff
from ffmpegio import streams

logging.basicConfig(level=logging.DEBUG)

mult_url = "tests/assets/testmulti-1m.mp4"
video_url = "tests/assets/testvideo-1m.mp4"
audio_url = "tests/assets/testaudio-1m.mp3"
outext = ".mp4"


def test_MediaReader():
    with streams.PipedFFmpegRunner.open_media_reader(
        [(mult_url, {})], None, options={"t_in": 1}, squeeze=False
    ) as reader:
        nframes = [0] * reader.num_output_streams
        for i, data in enumerate(reader):
            nframes = [n0 + v["shape"][0] for n0, v in zip(nframes, data)]

    assert nframes == [30, 44100, 25, 44100]


def test_MediaWriter_audio():
    ff.use("read_numpy")

    rates, data = ff.media.read(audio_url, t=1, ar=8000, sample_fmt="s16")

    with streams.PipedFFmpegRunner.open_media_encoder(
        [{"ar": rates["0:a:0"]}],
        [{"f": "matroska"}],
        show_log=True,
    ) as writer:
        for i, frame in enumerate(data.values()):
            writer.write(frame, i)
            # read the encoded bytes if any available
            b = writer.read_encoded_nowait(0)

        # close the input and wait for FFmpeg to finish encoding and terminate
        writer.wait(timeout=10)

        # read the rest
        b = writer.read_encoded(0)


def test_MediaWriter():
    ff.use("read_numpy")

    rates, data = ff.media.read(mult_url, t=1)
    stream_types = [spec.split(":", 2)[1] for spec in data]

    rate_opt_name = {"a": "ar", "v": "r"}
    stream_opts = [
        {rate_opt_name[mtype]: r} for mtype, r in zip(stream_types, rates.values())
    ]

    with streams.PipedFFmpegRunner.open_media_encoder(
        stream_opts,
        [{"f": "matroska", "map": range(len(stream_types))}],
        show_log=True,
    ) as writer:
        # write full audio streams
        video_frames = {}
        for i, (mtype, frame) in enumerate(zip(stream_types, data.values())):
            if mtype == "a":
                writer.write(frame, i)
            else:
                video_frames[i] = frame.shape[0]

        # write video stream one frame at a time
        frame_count = {k: 0 for k in video_frames}
        while any(
            n < nall for n, nall in zip(frame_count.values(), video_frames.values())
        ):
            for i, (mtype, frame) in enumerate(zip(stream_types, data.values())):
                if i in frame_count:
                    j = frame_count[i]
                    print(j)
                    try:
                        writer.write(frame[j], i)
                    except IndexError:
                        pass
                    else:
                        b = writer.read_encoded_nowait(0)
                        frame_count[i] = j + 1

        writer.wait(10)
        b = writer.read_encoded(-1)
        assert isinstance(b, bytes) and len(b) > 0


def test_SimpleMediaFilter():
    ff.use("read_numpy")

    fs, x = ff.audio.read("tests/assets/testaudio-1m.mp3", to=0.1)

    nin = 1024
    nblocks = len(x) // nin

    X = x[: nin * nblocks, ...].reshape(nblocks, nin, -1)

    with ff.streams.SISOFFmpegFilter.create_and_open(
        {"ar": fs},
        {"map": "[out]"},
        options={"filter_complex": "[0:a:0]showcqt=s=vga[out]"},
        show_log=True,
        squeeze=False,
    ) as f:
        # write the first frame (so the output rate is resolved)
        f.write(X[0])

        dt = nin / f.rate_in
        ntotal = int(nin * nblocks * f.rate / f.rate_in)  # total # of frames
        cumnout = np.astype(np.arange(1, nblocks) * dt * f.rate, int)
        nread = 0

        for i, (n, Xn) in enumerate(zip(cumnout, X[1:])):
            assert bool(f)

            ntry = n - nread
            if ntry > 0:
                out = f.read_nowait(n - nread)
                nread += out.shape[0]
                print(f"[{i:2}] expects {ntry} new frames, {out.shape[0]} frames read")
            f.write(Xn, last=i == nblocks - 2)

        ntry = ntotal - nread
        if ntry > 0:
            print(f"[last] reading the remaining {ntry} frames")
            out = f.read(ntry)
            nread += out.shape[0]
            print(f"[last] final read obtained {out.shape[0]} frames")
        assert nread == ntotal


def test_MediaFilter():
    ff.use("read_bytes")

    fs, x = ff.audio.read("tests/assets/testaudio-1m.mp3", to=1)

    fps, F = ff.video.read("tests/assets/testvideo-1m.mp4", to=1)

    print(f"video: {len(F['buffer'])} bytes | audio: {len(x['buffer'])} bytes")

    with ff.streams.PipedFFmpegRunner.open_media_filter(
        [{"r": fps}, {"r": fps}, {"ar": fs}, {"ar": fs}],
        output_streams=["[out0]", {"map": "[out1]"}],
        options={"filter_complex": ["[0:V:0][1:V:0]vstack", "[2:a:0][3:a:0]amerge"]},
        show_log=True,
        # loglevel="debug",
        # queuesize=4,
    ) as f:
        # f.write([F, F])
        for i, frame in enumerate([F, F, x, x]):
            f.write(frame, i, last=True)
        # sleep(1)

        assert ["out0", "out1"] == f.output_labels
        assert f.num_output_streams == 2

        frames_per_read = f.output_frames()
        nnext = list(frames_per_read)

        for i in range(F["shape"][0]):
            for st in range(2):
                n = int(nnext[st])
                Fout = f.read(n, st)
                print(Fout["shape"], n)
                # assert Fout["shape"][0] == n
                nnext[st] = nnext[st] - n + frames_per_read[st]

        # just in case
        f.wait(1)


def test_MediaTranscoder():
    url = "tests/assets/sample.mp4"

    data = b""

    # 1. transcode from a file to pipe
    with streams.PipedFFmpegRunner.open_media_transcoder(
        [],
        [{"f": "matroska", "to": 1}],
        extra_inputs=[(url, {})],
        show_log=True,
        # loglevel="debug",
    ) as f:
        while f:
            b = f.read_encoded_nowait(-1)
            data += b
        b = f.read_encoded_nowait(-1)
        data += b

        assert len(data) > 0

    print(f"FIRST TRANCODING YIELDED {len(data)} bytes")

    with streams.PipedFFmpegRunner.open_media_transcoder(
        [{}],
        [{"f": "flac", "vn": None}, {"f": "matroska", "codec": "copy"}],
        show_log=True,
        # loglevel="debug",
    ) as f:
        f.write_encoded(data, last=True)

        out = [b"", b""]

        while f:
            for st in range(2):
                out[st] += f.read_encoded_nowait(-1, stream=st)

    assert len(out[0]) > 0
    assert len(out[1]) > 0

    print(
        f"SECOND TRANCODING YIELDED {len(out[0])} bytes for flac and {len(out[1])} bytes for matroska"
    )
