from tempfile import TemporaryDirectory
from os import path
from pprint import pprint
import pytest

import ffmpegio as ff
import ffmpegio.filtergraph as fgb

url = "tests/assets/testmulti-1m.mp4"
url1 = "tests/assets/testvideo-1m.mp4"
url2 = "tests/assets/testaudio-1m.mp3"


@pytest.mark.parametrize(
    "urls,kwargs,nout",
    [
        ((url,), dict(t=1, show_log=True), 4),
        ((url,), dict(streams=("v:0", "v:1", "a:1", "a:0"), t=1, show_log=True), 4),
        ((url1, url2), dict(t=1, show_log=True), 2),
        ((url1,), dict(t=1, filter_complex="[0:0]split[out1][out2]", show_log=True), 2),
    ],
)
def test_media_read(urls, kwargs, nout):
    rates, data = ff.media.read(*urls, **kwargs)
    assert len(rates) == nout
    print(rates)
    print([(k, x["shape"], x["dtype"]) for k, x in data.items()])


def test_media_read_filter_complex():
    urls = (url2, url)  # aud + mul
    kwargs = dict(
        t=1,
        show_log=True,
        filter_complex="[0:a]aformat=f=dbl:r=8000:cl=mono;[1:v:1]setpts=0.5*PTS",
    )
    # kwargs = dict(map=(['[vout]','[aout]']), t=1, show_log=True, filter_complex='[0:a]aformat=f=dbl:r=8000:cl=mono[aout];[1:v:1]setpts=0.5*PTS[vout]')
    rates, data = ff.media.read(*urls, **kwargs)
    print(rates)
    print([(k, x["shape"], x["dtype"]) for k, x in data.items()])


def test_media_write():
    fs, x = ff.audio.read("tests/assets/testaudio-1m.mp3")

    fps, F = ff.video.read("tests/assets/testvideo-1m.mp4", vframes=120)

    outext = ".mp4"

    print(f"video: {len(F['buffer'])} bytes | audio: {len(x['buffer'])} bytes")

    with TemporaryDirectory() as tmpdirname:
        outfile = path.join(tmpdirname, f"out{outext}")
        ff.media.write(
            outfile, "va", (fps, F), (fs, x), show_log=True, shortest=ff.FLAG
        )

        pprint(ff.probe.format_basic(outfile))
        pprint(ff.probe.streams_basic(outfile))

@pytest.mark.skip(reason='To be implemented - merge_audio preset filtergraph needs more work.')
def test_media_write_audio_merge():
    stream1 = ff.audio.read("tests/assets/testaudio-1m.mp3", ar=8000, sample_fmt="s16")
    stream2 = ff.audio.read("tests/assets/testaudio-1m.mp3", ar=16000, sample_fmt="flt")
    stream3 = ff.audio.read("tests/assets/testaudio-1m.mp3", ar=4000, sample_fmt="dbl")

    outext = ".wav"

    fg = fgb.presets.merge_audio(["0:a", "1:a", "2:a"])
    with TemporaryDirectory() as tmpdirname:
        outfile = path.join(tmpdirname, f"out{outext}")
        ff.media.write(
            outfile,
            "aaa",
            stream1,
            stream2,
            stream3,
            filter_complex=fg,
            show_log=True,
            shortest=ff.FLAG,
        )
        pprint(ff.probe.format_basic(outfile))
        pprint(ff.probe.audio_streams_basic(outfile))


def test_media_filter():
    fs, x = ff.audio.read("tests/assets/testaudio-1m.mp3")

    fps, F = ff.video.read("tests/assets/testvideo-1m.mp4", vframes=120)

    print(f"video: {len(F['buffer'])} bytes | audio: {len(x['buffer'])} bytes")

    outrates, outdata = ff.media.filter(
        ["[0:V:0][1:V:0]vstack,split[out0]", "[2:a:0][3:a:0]amerge[out2]"],
        "vvaa",
        (fps, F),
        (fps, F),
        (fs, x),
        (fs, x),
        output_args={"[out0]": {},"out1":{}, "audio": {"map": "[out2]"}},
        show_log=True,
        shortest=ff.FLAG,
    )

    assert all(k in ("[out0]", "out1", "audio") for k in outrates)

    print(outrates)
