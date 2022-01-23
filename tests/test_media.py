from ffmpegio import ffmpegprocess, media
from ffmpegio.utils import avi
from io import BytesIO
import numpy as np
from matplotlib import pyplot as plt

if __name__ == "__main__":
    url = "tests/assets/testmulti-1m.mp4"
    rates, data = media.read(url)
    print(rates)
    print([(k, x.shape, x.dtype) for k, x in data.items()])
    # out = ffmpegprocess.run(
    #     {
    #         "inputs": [(url, None)],
    #         "outputs": [
    #             (
    #                 "-",
    #                 {
    #                     "ss": 0.1,
    #                     "t": 1,
    #                     "f": "avi",
    #                     "c:v": "rawvideo",
    #                     "pix_fmt": "ya8",
    #                     "c:a": "pcm_f32le",
    #                     "sample_fmt": "flt",
    #                 },
    #             )
    #         ],
    #         "global_options": None,
    #     },
    #     capture_log=False,
    # )
    # reader = avi.AviReader(BytesIO(out.stdout), True)
    # print(reader.streams)
    # n = len(reader.streams)
    # out = {v["spec"]: [] for v in reader.streams.values()}
    # for st, data in reader:
    #     out[st].append(data)
    # out = {k: np.concatenate(v) for k, v in out.items()}
    # print({k: (v.shape, v.dtype) for k, v in out.items()})

    # plt.imshow(out["v:0"][0, ..., 0], alpha=out["v:0"][0, ..., 1]/255)
    # plt.show()
