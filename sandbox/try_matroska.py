from ffmpegio import transcode, probe
from pprint import pprint

transcode(
    r"tests\assets\testmulti-1m.mp4",
    "sandbox/matroska.mkv",
    overwrite=True,
    show_log=True,
)
transcode(
    r"tests\assets\testmulti-1m.mp4",
    "sandbox/matroska_raw.mkv",
    overwrite=True,
    pix_fmt="rgb24",
    vcodec="rawvideo",
    sample_fmt="s16",
    acodec="pcm_s16le",
    allow_raw_vfw=1,
    show_log=True,
)
pprint(probe.full_details("sandbox/matroska_raw.mkv"))
