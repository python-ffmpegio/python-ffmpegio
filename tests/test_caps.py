import ffmpegio.caps as caps
from pprint import pprint

def test_all():
    filters = caps.filters()
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
    for demux in demuxes.keys():
        caps.demuxer_info(demux)
        break

    for mux in muxes.keys():
        caps.muxer_info(mux)
        break

    for enc in encs.keys():
        caps.encoder_info(enc)
        break

    for dec in decs.keys():
        caps.decoder_info(dec)
        break

    for filter in filters.keys():
        caps.filter_info(filter)
        break

    bsfs = caps.bsfilters()

    for bsf in bsfs:
        caps.bsfilter_info(bsf)
        break

def test_options():
    pprint(caps.options(name_only=True))
    pprint(caps.options('global'))
    pprint(caps.options('video',True))
    pprint(caps.options('per-file'))

if __name__ == '__main__':
    caps.encoder_info('mpeg1video')

