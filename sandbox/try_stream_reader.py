import time
from ffmpegio import ffmpeg, utils, audio, streams
from ffmpegio.ffmpegprocess import run
import subprocess as sp
from ffmpegio import io
import numpy as np

import PyQt5
from matplotlib import pyplot as plt

# import logging
# logging.basicConfig(level=logging.DEBUG)


url = "tests/assets/testaudio-1m.mp3"
sample_fmt = "s16"
out_codec, dtype = utils.get_audio_format(sample_fmt)
container = out_codec[4:]

fs, s = audio.read(url, sample_fmt=sample_fmt)

N = s.shape[0]
print(f"N={N}")
nread = 10000
T = nread / fs

# read random
reader = streams.SimpleAudioReader(url)

# while True:
#     x = reader.read(int(fs))
#     if x is None or not x.size:
#         break
#     print(x.shape)

for x in reader.readiter(int(fs)):
    print(x.shape)

reader.close()

# ntries = 10
# for n0 in (np.random.rand(ntries) * N).astype(int):
#     print(n0, n0 / fs, T)
#     args = {
#         "inputs": [(url, {"f": "mp3"})],
#         "outputs": [
#             ("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt, "ss": n0 / fs, "t": T})
#         ],
#     }

#     sout = run(args, shape=2, dtype=dtype, capture_log=False).stdout

#     print(np.sum(s[n0 : n0 + nread,:]-sout))

#     plt.plot(s[n0 : n0 + nread, :]- sout)
#     plt.show()
    
#     try:
#         assert np.allclose(s[n0 : n0 + nread], sout)
#     except:
#         nout = sout.size
#         assert False

    