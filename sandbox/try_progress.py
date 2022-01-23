import ffmpegio
from pprint import pprint
import tempfile
from os import path


def progress(status, done):
    pprint(status)


url = "tests/assets/testmulti-1m.mp4"

with tempfile.TemporaryDirectory() as tmpdirname:
    # print(probe.audio_streams_basic(url))
    out_url = path.join(tmpdirname, path.basename(url))

    ffmpegio.transcode(url, out_url, progress=progress)
