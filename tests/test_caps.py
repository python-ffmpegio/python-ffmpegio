import pytest
import ffmpegio.caps as caps
from pprint import pprint


def test_all():
    filters = caps.filters()
    assert "vstack" in filters
    caps.bsfilters()
    # print(filters)
    caps.codecs()
    encs = caps.encoders()
    decs = caps.decoders()
    caps.formats()
    caps.devices()
    muxes = caps.muxers()
    demuxes = caps.demuxers()
    caps.protocols()
    caps.pix_fmts()
    caps.sample_fmts()
    caps.layouts()
    caps.colors()


@pytest.mark.parametrize("name", caps.demuxers())
def test_demuxer(name):
    assert caps.demuxer_info(name) is not None


@pytest.mark.parametrize("name", caps.muxers())
def test_muxer(name):
    assert caps.muxer_info(name) is not None


@pytest.mark.parametrize("name", caps.encoders())
def test_encoder(name):
    assert caps.encoder_info(name) is not None


@pytest.mark.parametrize("name", caps.decoders())
def test_decoder(name):
    assert caps.decoder_info(name) is not None


@pytest.mark.parametrize("name", caps.filters())
def test_filter(name):
    info = caps.filter_info(name)
    assert isinstance(info, caps.FilterInfo)
    for opt in info.options:
        assert isinstance(opt, caps.FilterOption)


def test_filter_recall():
    assert caps.filter_info("vstack") == caps.filter_info("vstack")


@pytest.mark.parametrize("name", caps.bsfilters())
def test_bsf(name):
    assert isinstance(caps.bsfilter_info(name), caps.BSFInfo)


def test_options():
    pprint(caps.options(name_only=True))
    pprint(caps.options("global"))
    pprint(caps.options("video", True))
    pprint(caps.options("per-file"))


if __name__ == "__main__":
    caps.encoder_info("mpeg1video")
