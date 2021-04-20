from ffmpegio import image, probe, caps, ffmpeg
import tempfile, re
from os import path
import numpy as np
from matplotlib import pyplot as plt

url = "tests/assets/ffmpeg-logo.png"
outext = ".png"
# url = "tests/assets/testaudio-one.wav"
# url = "tests/assets/testaudio-two.wav"
# url = "tests/assets/testaudio-three.wav"
# url = "tests/assets/testvideo-5m.mpg"
# url = "tests/assets/testvideo-43.avi"
# url = "tests/assets/testvideo-169.avi"
# url = r"C:\Users\tikum\Music\(アルバム) [Jazz Fusion] T-SQUARE - T-Square Live featuring F-1 Grand Prix Theme [EAC] (flac+cue).mka"

info = probe.video_streams_basic(url)[0]
# info = probe.inquire(url)
print(info)

A = image.read(url)
print(A.dtype == np.uint8)
B = image.read(url,pix_fmt='ya8')
print(B.shape)
C = image.read(url,pix_fmt='rgb24')
D = image.read(url,pix_fmt='gray')
with tempfile.TemporaryDirectory() as tmpdirname:
    out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
    print(out_url, C.shape)
    image.write(out_url, C)
    print(probe.video_streams_basic(out_url))
    C = image.read(out_url,pix_fmt='rgba')

#     with open(path.join(tmpdirname, "progress.txt")) as f:
#         print(f.read())


# display = os.read(read_pipe, 128).strip()

plt.subplot(4,1,1)
plt.imshow(A)
plt.subplot(4,1,2)
plt.imshow(B[...,0],alpha=B[...,-1].astype(float)/255.0)
plt.subplot(4,1,3)
plt.imshow(C)
plt.subplot(4,1,4)
plt.imshow(D)
plt.show()
