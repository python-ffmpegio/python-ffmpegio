import pytest

# import ffmpegio as ff
# import ffmpegio.streams as ff_streams
from ffmpegio.streams.open import _parse_mode


@pytest.mark.parametrize(
    "mode,ret",
    [
        ("r", ("r", "", "")),
        ("w", ("w", "", "")),
        ("f", ("f", "", "")),
        ("d", ("d", "e", "")),
        ("e", ("e", "", "e")),
        ("t", ("t", "e", "e")),
        ("re", None),
        ("rav", ("r", "", "av")),
        ("avra", ("r", "", "ava")),
        ("wva", ("w", "va", "")),
        ("awv", ("w", "av", "")),
        ("dav", ("d", "e", "av")),
        ("eav", ("e", "av", "e")),
        ("ea->ev", None),
        ("ee->av", ("d", "ee", "av")),
        ("av->ee", ("e", "av", "ee")),
        ("av->va", ("f", "av", "va")),
    ],
)
def test_mode_parser(mode, ret):
    if ret is None:
        with pytest.raises(ValueError):
            _parse_mode(mode)
    else:
        assert _parse_mode(mode) == ret


# def test_fg():
#     with ff.open("color=c=red:d=1:r=10", "rv", f_in="lavfi", pix_fmt="rgb24") as f:
#         I = f.read(-1)
#     assert I["shape"][0] == 10


# url = "tests/assets/testmulti-1m.mp4"


# @pytest.mark.parametrize(
#     "src,mode,Cls",
#     [
#         (url, "rv", ff_streams.StdFFmpegRunner),
#         (url, "ra", ff_streams.StdFFmpegRunner),
#         (url, "e->v", ff_streams.PipedFFmpegRunner),
#         (url, "e->a", ff_streams.PipedFFmpegRunner),
#     ],
# )
# def test_readers(src, mode, Cls):

#     assert isinstance(ff.open(url, mode), Cls)


# def test_writers(): ...


# def test_filters(): ...


# def test_transcoders(): ...
