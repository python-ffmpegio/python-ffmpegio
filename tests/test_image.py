import re
import tempfile
from os import path

import pytest

from ffmpegio import filtergraph as fgb
from ffmpegio import image, transcode

outext = ".png"


def test_create():

    # make sure rgb channels are mapped properly
    A = image.create("color", c="red", s="100x100", d=1)
    assert A["shape"] == (100, 100, 3)
    assert A["dtype"] == ("|u1")
    # A = image.create("color", c="green", s="100x100", d=1)
    # A = image.create("color", c="blue", s="100x100", d=1)
    # B = image.create("cellauto")
    # B = image.create("allrgb", d=1)
    # B = image.create("allyuv", d=1)
    # B = image.create("gradients=s=1920x1080:x0=0:x1=0:y0=0:y1=1080", d=1)
    # B = image.create("gradients", d=1)
    # B = image.create("mandelbrot")
    # B = image.create("mptestsrc=t=dc_luma", d=1)
    # B = image.create("mptestsrc", t="ring1", d=1)
    # B = image.create("life", life_color="#00ff00")
    # B = image.create("haldclutsrc", 16, d=1)
    # A = image.create("testsrc", d=1)
    # B = image.create("testsrc2", alpha=0, d=1)
    # B = image.create("rgbtestsrc", d=1)
    # B = image.create("smptebars", d=1)
    # B = image.create("smptehdbars", d=1)
    # B = image.create("pal100bars", d=1)
    # B = image.create("pal75bars", d=1)
    # B = image.create("yuvtestsrc", d=1)
    # B = image.create("sierpinski")
    # print(A['dtype'], A['shape'])
    # plt.subplot(1,2,1)
    # plt.imshow(A)
    # plt.subplot(1,2,2)
    # plt.imshow(B)
    # plt.show()


def test_read_write():
    url = "tests/assets/ffmpeg-logo.png"
    outext = ".jpg"
    A = image.read(url)
    print(A["dtype"] == "|u1")
    B = image.read(url, pix_fmt="ya8")
    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        image.write(out_url, B)
        image.read(out_url, pix_fmt="rgba", show_log=True)

    #     with open(path.join(tmpdirname, "progress.txt")) as f:
    #         print(f.read())

    # display = os.read(read_pipe, 128).strip()

    # plt.subplot(4, 1, 1)
    # plt.imshow(A)
    # plt.subplot(4, 1, 2)
    # plt.imshow(B[..., 0], alpha=B[..., -1] / 255.0)
    # plt.subplot(4, 1, 3)
    # plt.imshow(C)
    # plt.subplot(4, 1, 4)
    # plt.imshow(D)
    # plt.show()


def test_read_basic_filter():

    url = "tests/assets/ffmpeg-logo.png"
    vf = fgb.presets.filter_video_basic(
        crop=(300, 50),
        flip="horizontal",
        transpose="clock",
    )
    image.read(url, show_log=True, vf=vf)


def test_filter():

    url = "tests/assets/ffmpeg-logo.png"
    I = image.read(url, vf=fgb.presets.remove_alpha("red", "rgb24"))
    vf = fgb.presets.filter_video_basic(
        crop=(10, 50),
        flip="horizontal",
        transpose="clock",
    )
    J = image.filter(vf, I, show_log=True)


@pytest.mark.parametrize(
    "fill_color,pix_fmt,ncomp",
    [("red", "rgb24", 3), ("red", None, 4), ("red", "gray", 0)],
)
def test_remove_alpha_filter(fill_color, pix_fmt, ncomp):

    url = "tests/assets/ffmpeg-logo.png"
    vf = fgb.presets.remove_alpha(fill_color=fill_color, pix_fmt=pix_fmt)
    print(str(vf))
    I = image.read(url, show_log=True, vf=vf)
    assert I["shape"] == ((100, 396, ncomp) if ncomp else (100, 396))


@pytest.fixture(scope="module")
def nonsquarepix_url():
    url = "tests/assets/testvideo-1m.mp4"
    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, path.basename(url))
        transcode(url, out_url, show_log=True, vf="setsar=11/13", t=0.5, pix_fmt="gray")
        yield out_url


@pytest.mark.parametrize(
    "mode", ["upscale", "downscale", "upscale_even", "downscale_even"]
)
def test_square_pixels(nonsquarepix_url, mode):

    vf = fgb.presets.square_pixels(mode)
    image.read(nonsquarepix_url, vf=vf, show_log=None)


if __name__ == "__main__":
    from matplotlib import pyplot as plt

    # logging.basicConfig(level=logging.DEBUG)

    url = "tests/assets/ffmpeg-logo.png"
    B = image.read(
        url,
        show_log=True,
        fill_color="red",
    )

    plt.imshow(B)
    plt.show()
