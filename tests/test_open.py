import pytest
import ffmpegio as ff
import ffmpegio.streams as ff_streams


def test_fg():
    with ff.open("color=c=red:d=1:r=10", "rv", f_in="lavfi", pix_fmt="rgb24") as f:
        I = f.read(-1)
    assert I["shape"][0] == 10


url = "tests/assets/testmulti-1m.mp4"


@pytest.mark.parametrize(
    "src,mode,Cls",
    [
        (url, "rv", ff_streams.SimpleVideoReader),
        (url, "ra", ff_streams.SimpleAudioReader),
        (url, "e->v", ff_streams.SimpleVideoReader),
        (url, "e->a", ff_streams.SimpleAudioReader),
    ],
)
def test_readers(src, mode, Cls):

    assert isinstance(ff.open(url, mode), Cls)


def test_writers(): ...


def test_filters(): ...


def test_transcoders(): ...
