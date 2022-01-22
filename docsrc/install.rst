.. highlight:: bash
.. _install:

Installation
============

To use :py:mod:`ffmpegio`, the package must be installed on Python as well as  
having the FFmpeg binary files at a location :py:mod:`ffmpegio` can find.

Install the :py:mod:`ffmpegio` package via :code:`pip`:

.. code-block::

   pip install ffmpegio

Install FFmpeg program
^^^^^^^^^^^^^^^^^^^^^^

The installation of FFmpeg is platform dependent. For Ubuntu/Debian Linux,

.. code-block::

   sudo apt install ffmpeg

and for MacOS,

.. code-block:: 

   brew install ffmpeg

no other actions are needed as these commands will place the FFmpeg executables 
on the system path. 

For Windows, it is a bit more complicated.

1. Download pre-built packages from the links available on the `FFmpeg's Download page
   <https://ffmpeg.org/download.html#build-windows>`__.
2. Unzip the content and place the files in one of the following directories:

   ==================================  ===============================================
   Auto-detectable FFmpeg folder path  Example
   ==================================  ===============================================
   ``%PROGRAMFILES%\ffmpeg``           ``C:\Program Files\ffmpeg``
   ``%PROGRAMFILES(X86)%\ffmpeg``      ``C:\Program Files (x86)\ffmpeg``
   ``%USERPROFILE%\ffmpeg``            ``C:\Users\john\ffmpeg``
   ``%APPDATA%\ffmpeg``                ``C:\Users\john\AppData\Roaming\ffmpeg``
   ``%APPDATA%\programs\ffmpeg``       ``C:\Users\john\AppData\Roaming\programs\ffmpeg``
   ``%LOCALAPPDATA%\ffmpeg``           ``C:\Users\john\AppData\Local\ffmpeg``
   ``%LOCALAPPDATA%\programs\ffmpeg``  ``C:\Users\john\AppData\Local\programs\ffmpeg``
   ==================================  ===============================================

   Keep the internal structure intact, i.e., the executables must be found at 
   ``ffmpeg\bin\ffmpeg.exe`` and ``ffmpeg\bin\ffprobe.exe``.

   There are two other alternative. First, the FFmpeg binaries could be placed on the 
   Python's current working directory (i.e., :code:`os.getcwd()`). Second, they could
   be placed in an arbitrary location and use :py:func:`ffmpegio.set_path` to
   specify the location. The latter feature is especially useful when `ffmpegio` is 
   bundled in a package (e.g., PyInstaller).

