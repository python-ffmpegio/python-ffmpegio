from ffmpegio import video, probe, caps, ffmpeg
import tempfile, re
from os import path
import numpy as np
from matplotlib import pyplot as plt

# url = "tests/assets/testvideo-5m.mpg"
url = "tests/assets/testvideo-43.avi"
# url = "tests/assets/testvideo-169.avi"
# url = r"C:\Users\tikum\Music\(アルバム) [Jazz Fusion] T-SQUARE - T-Square Live featuring F-1 Grand Prix Theme [EAC] (flac+cue).mka"
outext = ".mp4"

info = probe.video_streams_basic(url)[0]
# info = probe.inquire(url)
print(info)

fs, A = video.read(url, 10)
print(fs)
print(A.shape)

with tempfile.TemporaryDirectory() as tmpdirname:
    out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
    print(out_url)
    print(A.size)
    video.write(out_url, fs, A)
    print(probe.video_streams_basic(out_url))
    fs, A = video.read(out_url, 10)
    print(fs)
    print(A.shape)
