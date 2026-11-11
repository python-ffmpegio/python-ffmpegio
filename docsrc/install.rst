.. highlight:: bash
.. _install:

Installation
============

To use :code:`ffmpegio`, the package must be installed on Python as well as  
having the FFmpeg binary files at a location :code:`ffmpegio` can find. In addition,
optional external packages can be installed to enable the :code:`ffmpegio` features that interact 
with them.

Install the :code:`ffmpegio` package via :code:`pip`.

.. code-block::

   pip install ffmpegio

Install FFmpeg program
----------------------

There are two Python libraries to install FFmpeg for the use in Python:

The installation of FFmpeg is platform dependent. One platform agnostic approach
is to use our sister package: 
`ffmpeg-downloader <https://github.com/python-ffmpegio/python-ffmpeg-downloader>`__.

Install with `ffmpeg-downloader`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First, install the `ffmpegio-downloader` package, then run its cli command `ffdl`:

.. code-block:: 

   pip install ffmpeg-downloader
   ffdl install

If you wish to use the FFmpeg outside of `ffmpegio`, you can also install and add 
the installed directory to the user's system path (only for Windows and MacOS).

.. code-block:: 

   # optionally
   ffdl install --add-path

At a later date, you could re-run `ffdl` to look for an update (similar to `pip`):
I
.. code-block:: 

   ffdl install -U

Install on Ubuntu/Debian Linux
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block::

   sudo apt install ffmpeg

Install on MacOS
^^^^^^^^^^^^^^^^

.. code-block:: 

   brew install ffmpeg

Install on Windows
^^^^^^^^^^^^^^^^^^

It is a bit more complicated in Windows. 

1. Download pre-built packages from the links available on the `FFmpeg's Download page
   <https://ffmpeg.org/download.html#build-windows>`__.
2. Unzip the content and place the files in one of the following directories:

   ======================================  ===============================================
   Auto-detectable FFmpeg folder path      Example
   ======================================  ===============================================
   :code:`%PROGRAMFILES%\ffmpeg`           :code:`C:\Program Files\ffmpeg`
   :code:`%PROGRAMFILES(X86)%\ffmpeg`      :code:`C:\Program Files (x86)\ffmpeg`
   :code:`%USERPROFILE%\ffmpeg`            :code:`C:\Users\john\ffmpeg`
   :code:`%APPDATA%\ffmpeg`                :code:`C:\Users\john\AppData\Roaming\ffmpeg`
   :code:`%APPDATA%\programs\ffmpeg`       :code:`C:\Users\john\AppData\Roaming\programs\ffmpeg`
   :code:`%LOCALAPPDATA%\ffmpeg`           :code:`C:\Users\john\AppData\Local\ffmpeg`
   :code:`%LOCALAPPDATA%\programs\ffmpeg`  :code:`C:\Users\john\AppData\Local\programs\ffmpeg`
   ======================================  ===============================================

   Keep the internal structure intact, i.e., the executables must be found at 
   :code:`ffmpeg\bin\ffmpeg.exe` and :code:`ffmpeg\bin\ffprobe.exe`.

   There are two other alternative. First, the FFmpeg binaries could be placed on the 
   Python's current working directory (i.e., :code:`os.getcwd()`). Second, they could
   be placed in an arbitrary location and use :py:func:`ffmpegio.set_path` to
   specify the location. The latter feature is especially useful when `ffmpegio` is 
   bundled in a package (e.g., PyInstaller).

Basic Configuration Function References
=======================================

Basic Functions
---------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.ffmpeg_info
   ffmpegio.set_path
   ffmpegio.get_path
   ffmpegio.is_ready
   ffmpegio.use
   ffmpegio.using

.. autofunction:: ffmpegio.ffmpeg_info
.. autofunction:: ffmpegio.get_path
.. autofunction:: ffmpegio.set_path   
.. autofunction:: ffmpegio.is_ready
