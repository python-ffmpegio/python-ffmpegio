import ffmpegio.caps as caps

def test_all():
    filters = caps.filters()
    # print(filters)
    caps.codecs()
    encs = caps.coders("encoders")
    decs = caps.coders("decoders")
    caps.formats()
    caps.devices()
    muxes = caps.muxers()
    demuxes = caps.demuxers()
    caps.protocols()
    caps.pixfmts()
    caps.samplefmts()
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
