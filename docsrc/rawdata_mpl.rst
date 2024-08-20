`ffmpegio_plugin_mpl`: ffmpegio plugin to output matplotlib figures
===================================================================

|pypi| |pypi-status| |pypi-pyvers| |github-license| |github-status|

.. |pypi| image:: https://img.shields.io/pypi/v/ffmpegio
  :alt: PyPI
.. |pypi-status| image:: https://img.shields.io/pypi/status/ffmpegio
  :alt: PyPI - Status
.. |pypi-pyvers| image:: https://img.shields.io/pypi/pyversions/ffmpegio
  :alt: PyPI - Python Version
.. |github-license| image:: https://img.shields.io/github/license/python-ffmpegio/python-ffmpegio
  :alt: GitHub License
.. |github-status| image:: https://img.shields.io/github/workflow/status/python-ffmpegio/python-ffmpegio/Run%20Tests
  :alt: GitHub Workflow Status

This plugin enables Python `ffmpegio` package to output matplotlib's Figure.

Installation
------------

To enable it, install along with `ffmpegio-core` or `ffmpegio` package:

.. code-block:: bash

   pip install ffmpegio-core # or ffmpegio if also performing media I/O
   pip install ffmpegio-plugin-mpl

The plugin will be automatically loaded whenever `ffmpegio` package is imported.

Example
-------

Create an MP4 video of `Matplotlib's animation example <https://matplotlib.org/stable/gallery/animation/simple_anim.html>`__.

.. code-block:: python

  import ffmpegio
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


  with ffmpegio.open(
    "output.mp4", # output file name
    "wv", # open file in write-video mode
    1e3/interval, # framerate in frames/second
    pix_fmt="yuv420p", # specify the pixel format (default is yuv444p)
  ) as f:
      for n in range(save_count):
          animate(n) # update figure
          f.write(fig) # write new frame

