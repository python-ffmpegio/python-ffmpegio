from ffmpegio import image, probe
import tempfile, re
from os import path
import numpy as np

outext = ".png"
# url = "tests/assets/testaudio-one.wav"
# url = "tests/assets/testaudio-two.wav"
# url = "tests/assets/testaudio-three.wav"
# url = "tests/assets/testvideo-5m.mpg"
# url = "tests/assets/testvideo-43.avi"
# url = "tests/assets/testvideo-169.avi"


def test_create():
    # make sure rgb channels are mapped properly
    A = image.create("color", c="red", s="100x100")
    assert np.all(A[:, :, 1:] == 0)
    A = image.create("color", c="green", s="100x100")
    assert np.all(A[:, :, 0] == 0) and np.all(A[:, :, 2] == 0)
    A = image.create("color", c="blue", s="100x100")
    assert np.all(A[:, :, :-1] == 0)
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
        C = image.read(out_url, pix_fmt="rgba")

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