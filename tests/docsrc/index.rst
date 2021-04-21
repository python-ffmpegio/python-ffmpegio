Python Package: flacfile --- FLAC Audio File I/O
================================================

.. toctree::
   :maxdepth: 2

| PyPi: `<https://pypi.org/project/flacfile/>`__
| GitHub: `<https://github.com/hokiedsp/python-flacfile>`__

Introduction
------------

FLAC (Free Lossless Audio Codec) is an open-source lossless audio compression format developed by Josh Coalson
and now maintained by `Xiph.Org Foundation <https://xiph.org/flac/index.html>`__. It typically provides 50% to 70% 
reduction in the file size compared to WAV files without loss of information (source: `Wikipedia`_). The file format is
specified `here <flac_home>`_ and the source repository of the reference software is found `here <flac_git>`_.

Python :py:mod:`flacfile` package provides a pair of functions :py:func:`flacfile.read` and :py:func:`flacfile.write`
to access the FLAC files from Python using the reference encoder and decoder in Xiph.Org's `libFLAC <https://xiph.org/flac/api/index.html>`__
library. These functions are argument-compatible with :py:func:`scipy.io.wavfile.read` and :py:func:`scipy.io.wavfile.write`. 

.. _Wikipedia: https://en.wikipedia.org/wiki/FLAC
.. _flac_home: https://xiph.org/flac/index.html
.. _flac_git: https://gitlab.xiph.org/xiph/flac
.. _scipy.io.wavfile.read: https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.wavfile.read.html
.. _scipy.io.wavfile.write: https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.wavfile.write.html

Installation
------------

Install the package via pip:

.. code-block:: bash

   pip install flacfile

Package Contents
----------------
.. autofunction:: flacfile.read
.. autofunction:: flacfile.write
