"""Write Matplotlib :py:class:`Figure <matplotlib.figure.Figure>` (video only)

Creating Videos from Matplotlib figure
======================================

While Matplotlib supports video creation via its
`animation module <https://matplotlib.org/stable/users/explain/animations/animations.html>`__,
its interface is a bit cranky because its primary role is to animate the figure on screen
rather than outputting figures to a video file. You must create an animation object first before
saving it as a video.

:code:`ffmpegio` provides a direct method to write Matplotlib figure to a video write stream with
the same streaming interface as feeding the RGB frame data to FFmpeg.

Example
-------

Create an MP4 video of `Matplotlib's animation example <https://matplotlib.org/stable/gallery/animation/simple_anim.html>`__.

.. code-block:: python

  import ffmpegio as ff
  from matplotlib import pyplot as plt
  import numpy as np


  fig, ax = plt.subplots()

  x = np.arange(0, 2*np.pi, 0.01)
  line, = ax.plot(x, np.sin(x))

  interval=20 # delay in milliseconds
  save_count=50 # number of frames

  def animate(i):
      line.set_ydata(np.sin(x + i / 50))  # update the data.
      return line


  with ff.open(
    "output.mp4", # output file name
    "wv", # open file in write-video mode
    1e3/interval, # framerate in frames/second
    pix_fmt="yuv420p", # specify the pixel format (default is yuv444p)
    # add other ffmpeg options as keywod argument as needed
  ) as f:
      for n in range(save_count):
          animate(n) # update figure
          f.write(fig) # write new video frame

Any video format can be chosen with this interface and any FFmpeg options can be specified here.
For instance, an GIF animation of the above example can be created with optimized color pallette.
To do this, we use `palettegen <https://ffmpeg.org/ffmpeg-filters.html#palettegen>`__ and
`paletteuse <https://ffmpeg.org/ffmpeg-filters.html#paletteuse>`__` filters and construct a video filtergraph:

.. code-block::

  split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse

This filtergraph string could be provided directly to :code:`ff.open` as a `vf` keyword argument,
but let's use :code:`ffmpegio.filtergraph` submodule to construct it instead:

.. code-block:: python

  import ffmpegio.filtergraph as fgb

  vf = fgb.split() + fgb.palettegen() + fgb.paletteuse()

  with ff.open(
    "output.gif", # output file name
    "wv", # open file in write-video mode
    1e3/interval, # framerate in frames/second
    vf = vf # optimize the GIF palette
  ) as f:
      for n in range(save_count):
          animate(n) # update figure
          f.write(fig) # write new video frame

"""

from __future__ import annotations

import io

import matplotlib as Figure
from pluggy import HookimplMarker

from .._typing import DTypeString, Literal, ShapeTuple

__all__ = ["video_bytes", "video_info"]

hookimpl = HookimplMarker("ffmpegio")


@hookimpl
def video_info(obj: Figure) -> tuple[ShapeTuple, DTypeString]:
    """get video frame info

    :param obj: matplotlib Figure object
    :return shape: shape (height,width,components)
    :return dtype: data type in numpy dtype str expression
    """
    try:
        w, h = obj.canvas.get_width_height(physical=True)
        return (h, w, 4), "|u1"
    except:
        return None


@hookimpl
def video_bytes(obj: Figure) -> memoryview:
    """return bytes-like object of rawvideo NumPy array

    :param obj: video frame data with arbitrary number of frames
    :return: memoryview of video frames
    """

    try:
        with io.BytesIO() as io_buf:
            obj.savefig(io_buf, format="raw")
            io_buf.seek(0)
            return io_buf.getvalue()
    except:
        None


@hookimpl
def is_empty(obj: Figure) -> bool:
    """True if data blob object has no data

    :param obj: object containing media data
    """
    return False


@hookimpl
def video_frames(obj: Figure) -> Literal[1]:
    """get number of video frames in obj (always 1)

    :param obj: object containing video frame data with arbitrary number of frames
    :return: number of video frames in obj

    """

    return 1
