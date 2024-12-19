`ffmpegio-plugin-downloader`: An `ffmpegio` plugin to download latest FFmpeg release binaries
=============================================================================================

|pypi| |pypi-status| |pypi-pyvers| |github-license| |github-status|

.. |pypi| image:: https://img.shields.io/pypi/v/ffmpegio-plugin-downloader
  :alt: PyPI
.. |pypi-status| image:: https://img.shields.io/pypi/status/ffmpegio-plugin-downloader
  :alt: PyPI - Status
.. |pypi-pyvers| image:: https://img.shields.io/pypi/pyversions/ffmpegio-plugin-downloader
  :alt: PyPI - Python Version
.. |github-license| image:: https://img.shields.io/github/license/python-ffmpegio/python-ffmpegio-plugin-downloader
  :alt: GitHub License
.. |github-status| image:: https://img.shields.io/github/workflow/status/python-ffmpegio/python-ffmpegio-plugin-downloader/Run%20Tests
  :alt: GitHub Workflow Status

`Python ffmpegio <https://python-ffmpegio.github.io/python-ffmpegio/>`__ package aims to bring 
the full capability of `FFmpeg <https://ffmpeg.org>`__ to read, write, and manipulate multimedia 
data to Python. FFmpeg is an open-source cross-platform multimedia framework, which can handle 
most of the multimedia formats available today.

One caveat of FFmpeg is that there is no official program installer for Windows and MacOS (although 
`homebrew` could be used for the latter). `ffmpegio-plugin-downloader` adds a capability to download 
the latest release build of FFmpeg and enables the `ffmpegio` package to detect the paths of `ffmpeg`
and `ffprobe` automatically. This mechanism is supported by `ffmpeg-downloader <https://github.com/python-ffmpegio/python-ffmpeg-downloader>`__ 
package. Downloading of the release build must be performed interactively from the terminal screen, 
outside of Python.

Use
===

Install the package (which also installs `ffmpeg-downloader` package). Then, run `ffmpeg_downloader` to
download and install the latest release:

.. code-block:: bash

  pip install ffmpegio-core ffmpegio-plugin-downloader

  python -m ffmpeg_downloader # downloads and installs the latest release

Once the plugin and the FFmpeg executables are installed, `ffmpegio` will automatically
detect the downloaded executables.

At a later date, the installed FFmpeg can be updated to the latest release

.. code-block:: bash

  python -m ffmpeg_downloader -U # downloads and updates to the latest release

.. note::
  `ffmpegio-plugin-downloader` will *not* be activated if `ffmpeg` and `ffprobe` are 
  already available on the system PATH.
