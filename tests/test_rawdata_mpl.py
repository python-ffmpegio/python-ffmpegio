from os import path
from tempfile import TemporaryDirectory

import numpy as np
from matplotlib import pyplot as plt

import ffmpegio as ff


def iter_sliding_wform():

    nframes = 30
    nsample_per_frame = 1000
    n1max = nframes * nsample_per_frame

    nwin = 10 * nsample_per_frame
    ndelta = nwin // 2
    n0 = 0
    
    x = np.random.randn(n1max)

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
