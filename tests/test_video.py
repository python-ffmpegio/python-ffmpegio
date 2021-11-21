from ffmpegio import video, probe
import tempfile, re
from os import path
import numpy as np


def test_create():
    # make sure rgb channels are mapped properly
    A = video.create("mandelbrot", r=25, size="320x240", duration=10.0)
    assert A.shape == (250, 240, 320, 3)
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
    # print(A.dtype, A.shape)
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

    fs, A = video.read(url, 10)
    print(fs)
    print(A.shape)

    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        print(out_url)
        print(A.size)
        video.write(out_url, fs, A)
        print(probe.video_streams_basic(out_url))
        fs, A = video.read(out_url, 10)
        print(fs)
        print(A.shape)


def test_read():
    url = "tests/assets/testvideo-1m.mp4"
    outext = ".mp4"

    info = probe.video_streams_basic(url)[0]
    # info = probe.inquire(url)
    print(info)

    fs, A = video.read(url, 10)

    T = 10 / fs
    n0 = 2
    N = 5
    fs, B = video.read(url, 10, start=n0 / fs)
    assert np.array_equal(A[n0:, ...], B[: 10 - n0, ...])

    fs, C = video.read(url, start=n0 / fs, duration=N / fs)

    print(C.shape)
    assert np.array_equal(A[n0:n0+N, ...], C)

    fs, D = video.read(url, start=n0, duration=N, units='frames')
    assert np.array_equal(D, C)
