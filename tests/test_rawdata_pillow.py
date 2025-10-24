from tempfile import TemporaryDirectory
from os import path

import pytest

from PIL import Image, ImageSequence
import numpy as np

import ffmpegio as ff
from ffmpegio import plugins


def comp_images(im1, im2):
    return (
        im1.mode == im2.mode and im1.size == im2.size and im1.tobytes() == im2.tobytes()
    )


# test only with the base plugins
@pytest.fixture(scope="module", autouse=True)
def use_pillow():
    ff.use("read_pillow")
    assert ff.using("video") == "read_pillow"
    yield
    ff.use("read_bytes")


@pytest.fixture(scope="module")
def shape():
    return (120, 100)


@pytest.fixture(scope="module")
def base_image(shape):
    return Image.fromarray(np.random.randint(0, 256, (*shape, 4), np.uint8), "RGBA")


@pytest.mark.parametrize(
    "mode",
    ["L", "RGB", "RGBA", "F", "LA", "I;16L", "I;16B"],
)
def test_pillow_image(base_image, shape, mode):

    # create random test Image object
    image = base_image.convert(mode=mode)

    hook = plugins.get_hook()

    shape_in, dtype_in = hook.video_info(obj=image)

    assert shape == shape_in[:-1]

    b = hook.video_bytes(obj=image)
    image_out = hook.bytes_to_video(b=b, dtype=dtype_in, shape=shape_in, squeeze=False)

    assert comp_images(image_out[0], image)


def test_pillow_image_seq(shape):

    images = [
        Image.fromarray(np.random.randint(0, 256, (*shape, 4), np.uint8), "RGBA")
        for _ in range(10)
    ]

    hook = plugins.get_hook()

    shape_in, dtype_in = hook.video_info(obj=images)

    b = hook.video_bytes(obj=images)
    image_out = hook.bytes_to_video(
        b=b, dtype=dtype_in, shape=shape_in, squeeze=False
    )

    for fin, fout in zip(images, image_out):
        assert comp_images(fin, fout)


def test_pillow_avif():

    url = "tests/assets/testvideo-1m.mp4"

    hook = plugins.get_hook()

    with TemporaryDirectory() as tmpdir:
        avifpath = path.join(tmpdir, "test.avif")
        ff.transcode(url, avifpath, f="avif", r=1, to=10, show_log=True)
        with Image.open(avifpath) as image:
            shape_in, dtype_in = hook.video_info(obj=image)

            b = hook.video_bytes(obj=image)
            image_out = hook.bytes_to_video(
                b=b, dtype=dtype_in, shape=shape_in, squeeze=False
            )

            for fin, fout in zip(ImageSequence.Iterator(image), image_out):
                assert comp_images(fin, fout)
