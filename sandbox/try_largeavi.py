from math import prod
from ffmpegio import ffmpeg
from ffmpegio.utils import avi as aviutils
from os import path


r = 25

shape = (2160, 3840, 3)
s = f"{shape[1]}x{shape[0]}"
n = 2 ** 32 // prod(shape) + 1

outfile = r"sandbox\largeavi.avi"

if not path.exists(outfile):
    # create a short example with both audio & video
    pout = ffmpeg.exec(
        {
            "inputs": [(f"cellauto=rule=110:r={r}:s={s}", {"f": "lavfi"})],
            "outputs": [
                (
                    outfile,
                    {
                        "f": "avi",
                        "vcodec": "rawvideo",
                        "pix_fmt": "rgb24",
                        "acodec": "pcm_s16le",
                        "vframes": n,
                    },
                )
            ],
        },
        capture_log=False,
    )
    print(pout.returncode)

with open(outfile, "rb") as f:
    while True:
        try:
            id, datasize, chunksize, list_type = aviutils.read_chunk_header(f)
        except:
            break
        print(id, list_type)
        if not list_type:
            f.read(chunksize)

    f.seek(0)
    streams, hdrl = aviutils.read_header(f)
    while True:
        sid, data = aviutils.read_frame(f)
        print(sid, len(data))
