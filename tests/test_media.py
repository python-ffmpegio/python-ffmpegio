from ffmpegio import media


def test_media_read():
    url = "tests/assets/testmulti-1m.mp4"
    url1 = "tests/assets/testvideo-1m.mp4"
    url2 = "tests/assets/testaudio-1m.mp3"
    rates, data = media.read(url, t=1)
    rates, data = media.read(url, map=("v:0", "v:1", "a:1", "a:0"), t=1)
    rates, data = media.read(url1, url2, t=1)
    rates, data = media.read(url2, url, map=("1:v:0", (0, "a:0")), t=1)

    print(rates)
    print([(k, x['shape'], x['dtype']) for k, x in data.items()])


if __name__ == "__main__":
    from matplotlib import pyplot as plt

    pass
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
