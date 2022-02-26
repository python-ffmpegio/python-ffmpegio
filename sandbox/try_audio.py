import ffmpegio
from pprint import pprint

src = r"C:\Users\tikum\Music\(アルバム) [Jazz Fusion] T-SQUARE - T-Square Live featuring F-1 Grand Prix Theme [EAC] (flac+cue).mka"
dst = "sandbox/test.mp4"

pprint(ffmpegio.probe.audio_streams_basic(src)[0])

ffmpegio.transcode(
    src,
    dst,
    t_in=5,
    af="channelsplit=channel_layout=stereo:channels=FL",
    ac=1,
    overwrite=True,
    show_log=True,
)

pprint(ffmpegio.probe.audio_streams_basic(dst)[0])
