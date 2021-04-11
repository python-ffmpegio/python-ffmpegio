import ffmpegio.caps as caps

print("filters")
filters = caps.filters()
print(filters)
print("codecs")
print(caps.codecs())
print("coders")
encs = caps.coders("encoders")
print(encs)
decs = caps.coders("decoders")
print(decs)
print("formats")
print(caps.formats())
print("devices")
print(caps.devices())
print("muxers")
muxes = caps.muxers()
print(muxes)
print("demuxers")
demuxes = caps.demuxers()
print(demuxes)
print("protocols")
print(caps.protocols())
print("pixfmts")
print(caps.pixfmts())
print("samplefmts")
print(caps.samplefmts())
print("layouts")
print(caps.layouts())
print("colors")
print(caps.colors())
print("demuxer_info")
for demux in demuxes.keys():
    print(caps.demuxer_info(demux))
    break
print("muxer_info")
for mux in muxes.keys():
    print(caps.muxer_info(mux))
    break

print("encoder_info")
for enc in encs.keys():
    print(caps.encoder_info(enc))
    break

print("decoder_info")
for dec in decs.keys():
    print(caps.decoder_info(dec))
    break

print("filter_info")
for filter in filters.keys():
    print(caps.filter_info(filter))
    break
print("bsfilters")
bsfs = caps.bsfilters()
print(bsfs)
print("bsfilter_info")
for bsf in bsfs:
  print(caps.bsfilter_info(bsf))
  break
