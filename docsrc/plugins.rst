.. highlight:: python
.. _plugins:

Plugin Support
==============

There are three types of :py:mod:`ffmpegio` plugins:

.. table:: 
  :class: tight-table

  ===================== =====================================================
  FFmpeg Binary Finder  Search and return the path of the FFmpeg binary files
  Raw Media Output      Convert FFmpeg raw media bytes to a Python object
  Raw Media Input       Convert a Python object to FFmpeg raw media bytes
  ===================== =====================================================

Built-in Plugins
----------------

There are five built-in plugins, each interfacing with third-party Python packages:

.. table:: 
  :class: tight-table

  ==========================  ======  ==========================================================================
  Distro package name         Type    :code:`ffmpegio` features                                                 
  ==========================  ======  ==========================================================================
  :code:`numpy`               Out|In  Support Numpy array inputs and outputs instead of bytes                   
  :code:`matplotlib`          In      Support generation of images or videos from Matplotlib figure             
  :code:`pillow`              Out|In  Support :code:`PIL.Image.Image` as the input and output video frames     
  :code:`ffmepeg-downloader`  Find    Support the FFmpeg binaries installed by the :code:`ffdl install` command 
  :code:`static-ffmpeg`       Find    Support the FFmpeg binaries installed by :code:`static-ffmpeg`            
  ==========================  ======  ==========================================================================

Numpy
^^^^^

:py:mod:`ffmpegio` was originally designed to work with Numpy arrays, and as such
this plugin is chosen by default for media output over the  default ``bytes``-``dict``.


Matplotlib
^^^^^^^^^^

While Matplotlib supports video creation via its 
`animation module <https://matplotlib.org/stable/users/explain/animations/animations.html>`__,
its interface is a bit cranky because its primary role is to animate the figure on screen
rather than outputting figures to a video file. You must create an animation object first before
saving it as a video.

:code:`ffmpegio` provides a direct method to write Matplotlib figure to a video write stream with 
the same streaming interface as feeding the RGB frame data to FFmpeg.

For example, to create an MP4 video of `Matplotlib's animation example <https://matplotlib.org/stable/gallery/animation/simple_anim.html>`__.

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
  

ffmepeg-downloader
^^^^^^^^^^^^^^^^^^

To use this plugin, install the `ffmpeg-downloader` package by

.. code-block:: bash

  pip install ffmpeg_downloader

Then run the downloader's pip-like command-line tool to install FFmpeg:

.. code-block: bash

  ffdl install
  


Writing Custom Plugin
---------------------

TBD