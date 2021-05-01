from ffmpegio import transcode, probe
import tempfile, re
from os import path

def test_transcode():
    url = "tests/assets/testmulti-1m.mp4"
    outext = ".flac"

    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        # print(out_url)
        transcode(url, out_url, force=True)
        # print(probe.audio_streams_basic(out_url))
        # transcode(url, out_url)
        transcode(url, out_url, force=False)
        transcode(url, out_url, force=True)
        
        # with open(path.join(tmpdirname, "progress.txt")) as f:
        #     print(f.read())
