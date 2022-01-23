from ffmpegio import image, probe
import tempfile, re
from os import path
import numpy as np

from ffmpegio.utils.log import FFmpegError

outext = ".png"


def test_create():

    # make sure rgb channels are mapped properly
    A = image.create("color", c="red", s="100x100", d=1)
    assert np.all(A[:, :, 1:] == 0)
    A = image.create("color", c="green", s="100x100", d=1)
    assert np.all(A[:, :, 0] == 0) and np.all(A[:, :, 2] == 0)
    A = image.create("color", c="blue", s="100x100", d=1)
    assert np.all(A[:, :, :-1] == 0)
    B = image.create("cellauto")
    B = image.create("allrgb", d=1)
    B = image.create("allyuv", d=1)
    B = image.create("gradients=s=1920x1080:x0=0:x1=0:y0=0:y1=1080", d=1)
    B = image.create("gradients", d=1)
    B = image.create("mandelbrot")
    B = image.create("mptestsrc=t=dc_luma", d=1)
    B = image.create("mptestsrc", t="ring1", d=1)
    B = image.create("life", life_color="#00ff00")
    B = image.create("haldclutsrc", 16, d=1)
    A = image.create("testsrc", d=1)
    B = image.create("testsrc2", alpha=0, d=1)
    B = image.create("rgbtestsrc", d=1)
    B = image.create("smptebars", d=1)
    B = image.create("smptehdbars", d=1)
    B = image.create("pal100bars", d=1)
    B = image.create("pal75bars", d=1)
    B = image.create("yuvtestsrc", d=1)
    B = image.create("sierpinski")
    # print(A.dtype, A.shape)
    # plt.subplot(1,2,1)
    # plt.imshow(A)
    # plt.subplot(1,2,2)
    # plt.imshow(B)
    # plt.show()


def test_read_write():
    url = "tests/assets/ffmpeg-logo.png"
    outext = ".jpg"
    A = image.read(url)
    print(A.dtype == np.uint8)
    B = image.read(url, pix_fmt="ya8")
    print(B.shape)
    C = image.read(url, pix_fmt="rgb24")
    D = image.read(url, pix_fmt="gray")
    with tempfile.TemporaryDirectory() as tmpdirname:
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        print(out_url, C.shape)
        image.write(out_url, C)
        print(probe.video_streams_basic(out_url))
        C = image.read(out_url, pix_fmt="rgba", show_log=True)

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


# test_read_write()

if __name__ == "__main__":
    from matplotlib import pyplot as plt
    import logging
    from ffmpegio import utils, ffmpegprocess
    from ffmpegio.utils import filter as filter_utils, log as log_utils

    # logging.basicConfig(level=logging.DEBUG)

    url = "tests/assets/ffmpeg-logo.png"
    outext = ".jpg"
    B = image.read(
        url,
        show_log=True,
        pix_fmt="rgb24",
        fill_color="red",
        crop=(300, 50),
        flip="horizontal",
        transpose="clock",
    )

    B = image.read(
        url,
        show_log=True,
        s=(100,-2)
    )
    print(B.shape)

    plt.imshow(B)
    plt.show()
