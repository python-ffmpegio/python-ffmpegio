import builtins
from os import path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

import ffmpegio as ff
from ffmpegio.streams.BaseFFmpegRunner import (
    PipedFFmpegRunner,
    SISOFFmpegFilter,
    StdFFmpegRunner,
)

# import ffmpegio.streams as ff_streams
from ffmpegio.streams.open import (
    _parse_mode,
    open,
)


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
        ("fa", ("f", "a", "")),
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


@pytest.mark.parametrize(
    "mode,input_rates,data,cls",
    [
        ("fa", 8000, [np.zeros((128, 1), np.int16)], SISOFFmpegFilter),
        (
            "fva",
            [30, 8000],
            [np.zeros((100, 100, 1), np.uint8), np.zeros((128, 1), np.int16)],
            PipedFFmpegRunner,
        ),
    ],
)
def test_open_filter(mode, input_rates, data, cls):

    ff.use("read_numpy")

    opts = (
        {"input_shape": None, "input_dtype": None}
        if cls == SISOFFmpegFilter
        else {
            "input_options": None,
            "output_streams": None,
            "input_shapes": None,
            "input_dtypes": None,
            "primary_output": None,
        }
    )

    with open(
        "-",
        mode,
        input_rates,
        **opts,
        squeeze=False,
        extra_inputs=None,
        extra_outputs=None,
        blocksize=None,
        enc_blocksize=None,
        queuesize=None,
        timeout=None,
        progress=None,
        show_log=False,
        sp_kwargs=None,
        to=1,
        r=20,
        ar=4000,
    ) as runner:
        for i, blob in enumerate(data):
            runner.write(blob, stream=i)
        assert isinstance(runner, cls)
        assert runner.readable
        assert runner.writable
        assert not runner.decodable
        assert not runner.encodable


def test_open_decoder():

    with builtins.open(url, "rb") as f:
        b = f.read(1024)

    with open(
        "-",
        "e->a",
        ouput_streams=None,
        squeeze=False,
        extra_inputs=None,
        extra_outputs=None,
        primary_output=None,
        blocksize=None,
        enc_blocksize=None,
        queuesize=None,
        timeout=None,
        progress=None,
        show_log=False,
        sp_kwargs=None,
        to=1,
    ) as runner:
        runner.write_encoded(b)
        assert isinstance(runner, PipedFFmpegRunner)
        assert runner.readable
        assert not runner.writable
        assert runner.decodable
        assert not runner.encodable


def test_open_encoder():

    with open(
        "-",
        "a->e",
        8000,
        input_options=None,
        output_options=None,
        extra_inputs=None,
        extra_outputs=None,
        input_shapes=None,
        input_dtypes=None,
        enc_blocksize=None,
        queuesize=None,
        timeout=None,
        progress=None,
        show_log=False,
        sp_kwargs=None,
        to=1,
    ) as runner:
        assert isinstance(runner, PipedFFmpegRunner)
        assert not runner.readable
        assert runner.writable
        assert not runner.decodable
        assert runner.encodable


def test_open_transcoder():

    with open(
        "-",
        "e->e",
        input_options=None,
        output_options=None,
        extra_inputs=None,
        extra_outputs=None,
        enc_blocksize=None,
        queuesize=None,
        timeout=None,
        progress=None,
        show_log=False,
        sp_kwargs=None,
        to=1,
    ) as runner:
        assert isinstance(runner, PipedFFmpegRunner)
        assert not runner.readable
        assert not runner.writable
        assert runner.decodable
        assert runner.encodable
