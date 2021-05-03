from shutil import ignore_patterns
from sys import stderr
import pytest
from ffmpegio import ffmpeg, probe
import tempfile, re
from os import path


def test_ffmpeg():
    out = ffmpeg.parse("ffmpeg -i input.avi -b:v 64k -bufsize 64k output.avi")
    assert out == {
        "_global_options": {},
        "inputs": [("input.avi", {})],
        "outputs": [("output.avi", {"b:v": "64k", "bufsize": "64k"})],
    }

    s = r"ffmpeg -i input.ts -filter_complex \
    '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
    -sn -map '#0x2dc' -map a output.mkv"
    assert ffmpeg.parse(s) == {
        "_global_options": {
            "filter_complex": "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay"
        },
        "inputs": [("input.ts", {})],
        "outputs": [("output.mkv", {"sn": None, "map": ["#0x2dc", "a"]})],
    }

    s = "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k /tmp/a.mp2 -map 0:a -b:a 128k /tmp/b.mp2"
    p = ffmpeg.parse(s)
    assert p == {
        "_global_options": {},
        "inputs": [("/tmp/a.wav", {})],
        "outputs": [
            ("/tmp/a.mp2", {"map": "0:a", "b:a": "64k"}),
            ("/tmp/b.mp2", {"map": "0:a", "b:a": "128k"}),
        ],
    }


def test_parse_options():
    s = r"-filter_complex \
    '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
    -sn -map '#0x2dc'"
    ffmpeg.parse_options(s) == {
        "filter_complex": "\n",
        "#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay": "\n",
        "sn": None,
        "map": "#0x2dc",
    }

    s = "-i /tmp/a.wav -map 0:a -map 1:a -map 1:v -b:a 64k"
    p = ffmpeg.parse_options(s)
    assert p == {"i": "/tmp/a.wav", "map": ["0:a", "1:a", "1:v"], "b:a": "64k"}

    def test_compose():
        assert ffmpeg.compose(
            {}, [("input.avi", {})], [("output.avi", {"b:v": "64k", "bufsize": "64k"})]
        ) == ["-i", "input.avi", "-b:v", "64k", "-bufsize", "64k", "output.avi"]

        assert ffmpeg.compose(
            {
                "filter_complex": "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay"
            },
            [("input.ts", {})],
            [("output.mkv", {"sn": None, "map": ["#0x2dc", "a"]})],
            command="ffmpeg",
        ) == [
            "ffmpeg",
            "-filter_complex",
            "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay",
            "-i",
            "input.ts",
            "-sn",
            "-map",
            "#0x2dc",
            "-map",
            "a",
            "output.mkv",
        ]

    assert (
        ffmpeg.compose(
            inputs=[("/tmp/a.wav", {})],
            outputs=[
                ("/tmp/a test.mp2", {"map": "0:a", "b:a": "64k"}),
                ("/tmp/b.mp2", {"map": "0:a", "b:a": "128k"}),
            ],
            command="ffmpeg",
            shell_command=True,
        )
        == "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k '/tmp/a test.mp2' -map 0:a -b:a 128k /tmp/b.mp2"
    )


def test_find():
    print(ffmpeg.find())  # gotta have ffmpeg to run the tests
    with pytest.raises(Exception):
        ffmpeg.find("wrong_dir")


def test_found():
    assert ffmpeg.found()  # assuming ffmpeg is found in a default place


def test_where():
    assert ffmpeg.where() is not None  # assuming ffmpeg is found


def test_versions():
    assert "version" in ffmpeg.versions()


def test_run_sync():
    ffmpeg.run_sync("-help")


def test_run():
    proc = ffmpeg.run("-help")
    proc.communicate()
    proc.wait()


def test_probe():
    ffmpeg.ffprobe("-help")


import logging

logging.basicConfig(level=logging.DEBUG)


if __name__ == "__main__":

    from pprint import pprint

    url = "tests/assets/testvideo-5m.mpg"
    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", ".mp4", path.basename(url)))

        args = {
            "inputs": [(url, {"t": 10.0})],
            "outputs": [(out_url, None)],
            # "outputs": [(out_url, {"vcodec": "bad"})],
        }

        proc = ffmpeg.run(args, progress=lambda d, done: pprint(d))

        while proc.poll() is None:
            # time.sleep(0.01)
            # print(stderr_monitor.output.readline())
            txt = proc.stderr.readline()
            if txt:
                print(txt[:-1])

        if proc.returncode != 0:
            raise Exception(proc.get_errmsg())

# progress=continue
# frame=998
# fps=116.80
# stream_0_0_q=-1.0
# bitrate= 489.3kbits/s
# total_size=4069415
# out_time_us=66532381
# out_time_ms=66532381
# out_time=00:01:06.532381
# dup_frames=0
# drop_frames=993
# speed=7.79x
# progress=end

# tests/assets/testvideo-5m.mpg.bad: No such file or directory

# Input #0, mpegts, from 'tests/assets/testvideo-5m.mpg':
#   Duration: 00:01:06.40, start: 0.040000, bitrate: 584 kb/s
#   Program 1
#   Stream #0:0[0x3e9]: Audio: mp2 ([3][0][0][0] / 0x0003), 44100 Hz, stereo, fltp, 64 kb/s
#   Stream #0:1[0x3ea]: Video: h264 (Main) ([27][0][0][0] / 0x001B), yuv420p(progressive), 352x240 [SAR 1:1 DAR 22:15], 14.99 fps, 29.97 tbr, 90k tbn, 29.97 tbc
# Unknown encoder 'bad'

# [mpegts @ 000001a82e83b540] DTS 6603 < 12609 out of order
# Input #0, mpegts, from 'tests/assets/testvideo-5m.mpg':
#   Duration: 00:01:06.40, start: 0.040000, bitrate: 584 kb/s
#   Program 1
#   Stream #0:0[0x3e9]: Audio: mp2 ([3][0][0][0] / 0x0003), 44100 Hz, stereo, fltp, 64 kb/s
#   Stream #0:1[0x3ea]: Video: h264 (Main) ([27][0][0][0] / 0x001B), yuv420p(progressive), 352x240 [SAR 1:1 DAR 22:15], 14.99 fps, 29.97 tbr, 90k tbn, 29.97 tbc
# Stream mapping:
#   Stream #0:1 -> #0:0 (h264 (native) -> h264 (libx264))
#   Stream #0:0 -> #0:1 (mp2 (native) -> aac (native))
# Press [q] to stop, [?] for help
# [libx264 @ 000001a82e856e00] using SAR=1/1
# [libx264 @ 000001a82e856e00] using cpu capabilities: MMX2 SSE2Fast SSSE3 SSE4.2 AVX FMA3 BMI2 AVX2
# [libx264 @ 000001a82e856e00] profile High, level 1.2, 4:2:0, 8-bit
# [libx264 @ 000001a82e856e00] 264 - core 161 r3048 b86ae3c - H.264/MPEG-4 AVC codec - Copyleft 2003-2021 - http://www.videolan.org/x264.html - options: cabac=1
# ref=3 deblock=1:0:0 analyse=0x3:0x113 me=hex subme=7 psy=1 psy_rd=1.00:0.00 mixed_ref=1 me_range=16 chroma_me=1 trellis=1 8x8dct=1 cqm=0 deadzone=21,11 fast_pskip=1 chroma_qp_offset=-2 threads=6 lookahead_threads=1 sliced_threads=0 nr=0 decimate=1 interlaced=0 bluray_compat=0 constrained_intra=0 bframes=3 b_pyramid=2 b_adapt=1 b_bias=0 direct=1 weightb=1 open_gop=0 weightp=2 keyint=250 keyint_min=14 scenecut=40 intra_refresh=0 rc_lookahead=40 rc=crf mbtree=1 crf=23.0 qcomp=0.60 qpmin=0 qpmax=69 qpstep=4 ip_ratio=1.40 aq=1:1.00
# Output #0, mp4, to 'C:\Users\tikuma\AppData\Local\Temp\tmpgs5d2mft\testvideo-5m.mp4':
#   Metadata:
#     encoder         : Lavf58.76.100
#   Stream #0:0: Video: h264 (avc1 / 0x31637661), yuv420p(progressive), 352x240 [SAR 1:1 DAR 22:15], q=2-31, 14.98 fps, 11988 tbn
#     Metadata:
#       encoder         : Lavc58.134.100 libx264
#     Side data:
#       cpb: bitrate max/min/avg: 0/0/0 buffer size: 0 vbv_delay: N/A
#   Stream #0:1: Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s
#     Metadata:
#       encoder         : Lavc58.134.100 aac
# frame=  998 fps=175 q=-1.0 Lsize=    3974kB time=00:01:06.53 bitrate= 489.3kbits/s dup=0 drop=993 speed=11.7x
# video:2895kB audio:1044kB subtitle:0kB other streams:0kB global headers:0kB muxing overhead: 0.883014%
# [libx264 @ 000001a82e856e00] frame I:30    Avg QP:20.17  size:  6239
# [libx264 @ 000001a82e856e00] frame P:293   Avg QP:22.67  size:  4361
# [libx264 @ 000001a82e856e00] frame B:675   Avg QP:25.30  size:  2221
# [libx264 @ 000001a82e856e00] consecutive B-frames:  7.3%  4.8%  8.1% 79.8%
# [libx264 @ 000001a82e856e00] mb I  I16..4: 31.1% 29.5% 39.4%
# [libx264 @ 000001a82e856e00] mb P  I16..4: 19.2% 15.6% 18.7%  P16..4: 19.0%  9.2%  4.7%  0.0%  0.0%    skip:13.6%
# [libx264 @ 000001a82e856e00] mb B  I16..4:  2.7%  2.9%  6.8%  B16..8: 26.4%  9.1%  2.9%  direct: 6.6%  skip:42.7%  L0:43.8% L1:44.4% BI:11.8%
# [libx264 @ 000001a82e856e00] 8x8 transform intra:27.4% inter:31.1%
# [libx264 @ 000001a82e856e00] coded y,uvDC,uvAC intra: 50.8% 78.5% 54.7% inter: 18.1% 35.1% 13.3%
# [libx264 @ 000001a82e856e00] i16 v,h,dc,p: 19% 56% 13% 12%
# [libx264 @ 000001a82e856e00] i8 v,h,dc,ddl,ddr,vr,hd,vl,hu: 19% 34% 25%  4%  3%  3%  3%  3%  6%
# [libx264 @ 000001a82e856e00] i4 v,h,dc,ddl,ddr,vr,hd,vl,hu: 17% 26% 17%  7%  6%  5%  8%  5%  9%
# [libx264 @ 000001a82e856e00] i8c dc,h,v,p: 31% 41% 16% 13%
# [libx264 @ 000001a82e856e00] Weighted P-Frames: Y:8.2% UV:5.5%
# [libx264 @ 000001a82e856e00] ref P L0: 61.3% 12.9% 16.0%  9.3%  0.5%
# [libx264 @ 000001a82e856e00] ref B L0: 88.0%  9.2%  2.8%
# [libx264 @ 000001a82e856e00] ref B L1: 96.2%  3.8%
# [libx264 @ 000001a82e856e00] kb/s:356.03
# [aac @ 000001a830554bc0] Qavg: 138.940
