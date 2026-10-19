from os import path
from tempfile import TemporaryDirectory

import numpy as np
from matplotlib import pyplot as plt

import ffmpegio as ff


def iter_sliding_wform(x=None, nsample_per_frame=1000, nframes=30, nwin=10000):

    if x is None:
        n1max = nframes * nsample_per_frame
        x = np.random.randn(n1max)
    else:
        n1max = len(x)
        if nsample_per_frame > n1max:
            nframes = 1
            nsample_per_frame = n1max
        elif nframes * nsample_per_frame != n1max:
            nframes = n1max // nsample_per_frame

    ndelta = nwin // 2
    n0 = 0

    fig, ax = plt.subplots(
        1,
        1,
        facecolor="k",
        gridspec_kw=dict(left=0, bottom=0, right=1, top=1),
        subplot_kw=dict(frameon=False, xmargin=0, xticks=[], yticks=[]),
    )
    try:
        hcur = ax.axvline(0, c="y", lw=1)
        ax.plot(x, lw=0.5, c="w")

        for k in range(nframes):
            n = round(k * nsample_per_frame)

            if n < ndelta:
                n0 = 0
            elif n > n1max - ndelta:
                n0 = n1max - nwin
            else:
                n0 = n - ndelta
            ax.set_xlim(n0, n0 + nwin)
            hcur.set_xdata([n, n])
            fig.canvas.draw()
            yield fig
    finally:
        plt.close(fig)


def test_mpl_image():

    with TemporaryDirectory() as tmpdir:
        pngfile = path.join(tmpdir, "test.png")
        for fig in iter_sliding_wform():
            ff.image.write(pngfile, fig)


def test_mpl_video():

    with (
        TemporaryDirectory() as tmpdir,
        ff.open(path.join(tmpdir, "test.mp4"), "wv", input_rate=30) as f,
    ):
        for fig in iter_sliding_wform():
            f.write(fig)


def test_mpl_va():

    fs = 12000
    duration = 1 / 3

    n = round(duration * fs)
    f = 1000
    x = np.sin(2 * np.pi * f * np.arange(n) / fs)

    fps = 30
    nsample_per_frame = fs // fps
    nframes = round(fps * duration)
    nwin = n

    with TemporaryDirectory() as tmpdir:
        with (
            ff.open(
                mp4file := path.join(tmpdir, "test.mp4"), "wva", input_rates=[fps, fs]
            ) as f,
        ):
            f.write(x, stream=1)
            for fig in iter_sliding_wform(x, nsample_per_frame, nframes, nwin):
                f.write(fig, stream=0)

        info = ff.probe.full_details(mp4file)
        st = info["streams"][0]
        assert st["codec_type"] == "video"
        assert st["nb_frames"] == nframes
        st = info["streams"][1]
        assert st["codec_type"] == "audio"
