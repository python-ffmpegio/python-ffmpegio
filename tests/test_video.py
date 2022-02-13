from math import prod
from ffmpegio import video, probe
import tempfile, re
from os import path
import numpy as np


def test_create():
    # make sure rgb channels are mapped properly
    A = video.create("mandelbrot", r=25, size="320x240", t_in=10)[1]
    assert A["shape"] == (250, 240, 320, 3)
    # B = image.create("allrgb")
    # B = image.create("allyuv")
    # B = image.create("gradients=s=1920x1080:c0=000000:c1=434343:x0=0:x1=0:y0=0:y1=1080")
    # B = image.create("gradients")
    # B = image.create("mandelbrot")
    # B = image.create("mptestsrc=t=dc_luma")
    # B = image.create("mptestsrc", t="ring1")
    # B = image.create("life",life_color='red')
    # B = image.create("haldclutsrc",16)
    # A = image.create("testsrc")
    # B = image.create("testsrc2",alpha=0)
    # B = image.create("rgbtestsrc")
    # B = image.create("smptebars")
    # B = image.create("smptehdbars")
    # B = image.create("pal100bars")
    # B = image.create("pal75bars")
    # B = image.create("yuvtestsrc")
    # B = image.create("sierpinski")
    # print(A['dtype'], A['shape'])
    # plt.subplot(1,2,1)
    # plt.imshow(A)
    # plt.subplot(1,2,2)
    # plt.imshow(B)
    # plt.show()


def test_read_write():
    url = "tests/assets/testvideo-1m.mp4"
    outext = ".mp4"

    info = probe.video_streams_basic(url)[0]
    # info = probe.inquire(url)
    print(info)

    fs, A = video.read(url, vframes=10)
    print(fs)
    print(A["shape"])

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        print(out_url)
        print(prod(A["shape"]))
        video.write(out_url, fs, A)
        print(probe.video_streams_basic(out_url))
        fs, A = video.read(out_url, vframes=10)
        print(fs)
        print(A["shape"])


def test_read():
    url = "tests/assets/testvideo-1m.mp4"
    outext = ".mp4"

    info = probe.video_streams_basic(url)[0]
    # info = probe.inquire(url)
    print(info)

    fs, A = video.read(url, vframes=10)

    T = 10 / fs
    n0 = 2
    N = 5
    fs, B = video.read(url, vframes=10, ss_in=float(n0 / fs))
    print(B["shape"], A["shape"])
    nbytes = prod(A["shape"][1:]) * int(A["dtype"][-1])
    assert A["buffer"][n0 * nbytes :] == B['buffer'][: (10 - n0) * nbytes]

    fs, C = video.read(url, ss_in=float(n0 / fs), t_in=float(N / fs))

    print(C["shape"])
    assert A["buffer"][n0 * nbytes :(n0+N)*nbytes] == C['buffer']
    
    # fs, D = video.read(url, ss_in=n0, t_in=N, units='frames')
    # assert np.array_equal(D, C)


def test_filter():
    r_in, input = video.create("life", life_color="Red", t_in=1)
    print("input", input["shape"], input["dtype"])
    expr = "edgedetect"
    print(r_in, input["shape"], input["dtype"])
    r, output = video.filter(expr, r_in, input)
    print(r, output["shape"], output["dtype"])


def test_two_pass_write():
    url = "tests/assets/testmulti-1m.mp4"
    fs, A = video.read(url, vframes=100)
    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, path.basename(url))
        video.write(
            out_url,
            fs,
            A,
            two_pass=True,
            **{"c:v": "libx264", "b:v": "500k"},
            show_log=True
        )


if __name__ == "__main__":
    # test_create()
    from ffmpegio import configure, utils, ffmpegprocess
    from ffmpegio.utils import log as log_utils
    import numpy as np
    from pprint import pprint
    import re

    # ffmpeg -y -i input -c:v libx264 -b:v 2600k -pass 1 -an -f null /dev/null && \
    # ffmpeg -i input -c:v libx264 -b:v 2600k -pass 2 -c:a aac -b:a 128k output.mp4
    import logging

    logging.basicConfig(level=logging.DEBUG)

    test_two_pass_write()
