from os import path
from tempfile import TemporaryDirectory

import pytest

from ffmpegio.streams.BaseFFmpegRunner import (
    PipedFFmpegRunner,
    SISOFFmpegFilter,
    StdFFmpegRunner,
)

# import ffmpegio as ff
# import ffmpegio.streams as ff_streams
from ffmpegio.streams.open import _parse_mode, open


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


url = "tests/assets/testmulti-1m.mp4"


@pytest.mark.parametrize(
    "mode,output_streams,cls",
    [
        ("ra", ["0:a:0"], StdFFmpegRunner),
        ("rva", ["0:v:0", "0:a:0"], PipedFFmpegRunner),
    ],
)
def test_open_reader(mode, output_streams, cls):
    runner = open(
        url,
        mode,
        ouput_streams=output_streams,
        squeeze=False,
        extra_outputs=None,
        blocksize=None,
        progress=None,
        show_log=False,
        sp_kwargs=None,
        to=1,
    )
    assert isinstance(runner, cls)
    assert runner.readable
    assert not runner.writable
    assert not runner.decodable
    assert not runner.encodable


@pytest.mark.parametrize(
    "mode,input_rates,cls",
    [
        ("wa", 8000, StdFFmpegRunner),
        ("wva", [30, 8000], PipedFFmpegRunner),
    ],
)
def test_open_writer(mode, input_rates, cls):

    opts = (
        {"input_shape": None, "input_dtype": None}
        if cls == StdFFmpegRunner
        else {
            "input_options": None,
            "input_shapes": None,
            "input_dtypes": None,
            "enc_blocksize": None,
            "queuesize": None,
            "timeout": None,
        }
    )

    with TemporaryDirectory() as tmpdirname:
        outfile = path.join(tmpdirname, "out.mp4")
        with open(
            outfile,
            mode,
            input_rates,
            **opts,
            extra_inputs=None,
            progress=None,
            show_log=False,
            overwrite=True,
            sp_kwargs=None,
            to=1,
        ) as runner:
            assert isinstance(runner, cls)
            assert not runner.readable
            assert runner.writable
            assert not runner.decodable
            assert not runner.encodable

    SISOFFmpegFilter
    # siso filter
    # mimo filter
    # decoder
    # encoder
    # transcoder
