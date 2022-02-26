from fractions import Fraction
from ffmpegio import probe, FilterGraph
from pprint import pprint

infiles = [
    r"tests\assets\testvideo-1m.mp4",
    r"tests\assets\testmulti-1m.mp4",
    r"tests\assets\testvideo-1m.mp4",
]
outfile = "sandbox/temp.mp4"

# anullsrc options (make sure this matches with the existing audio streams)
channel_layout = "stereo"
sample_rate = 44100


def check_stream(file):
    info = probe.streams_basic(file)
    vinfo = next((info for info in info if info["codec_type"] == "video"))
    ast, ainfo = next(
        ((i, info) for i, info in enumerate(info) if info["codec_type"] == "audio"),
        (None, None),
    )
    has_noaudio = ast is None
    tinfo = vinfo if has_noaudio else ainfo
    duration = tinfo["duration_ts"] * Fraction(tinfo["time_base"])
    return has_noaudio, duration


st_info = [check_stream(infile) for infile in infiles]

anullsrcs = [
    ("anullsrc", channel_layout, sample_rate, {"duration": duration})
    if has_noaudio
    else None
    for (has_noaudio, duration) in st_info
]

filt_specs = [[spec] for spec in anullsrcs if spec is not None]
filt_specs.append([("concat", len(infiles), 1, 1)])
M = len(filt_specs)
input_labels = {
    f"{i}:{ctype}": (M, 0, 2 * i + j)
    for j, ctype in enumerate(("v", "a"))
    for i, src in enumerate(anullsrcs)
    if ctype != "a" or src is None
}
output_labels = {"vout": (M, 0, 0), "aout": (M, 0, 1)}
links = {
    (M, 0, 2 * i + 1): (i, 0, 0) for i, src in enumerate(anullsrcs) if src is not None
}
pprint(links)

links = {}
pprint(filt_specs)

fg = FilterGraph([["anullsrc"]])

#                                      vcodec='libx264',
#                                      acodec='aac')
