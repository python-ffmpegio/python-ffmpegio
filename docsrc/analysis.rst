.. py:currentmodule:: ffmpegio.analyze
.. highlight:: python
.. _analyze:

***********************************************************
:py:mod:`ffmpegio.analyze`: Frame Metadata Analysis Module
***********************************************************

There are a number of `FFmpeg filters <https://ffmpeg.org/ffmpeg-filters.html>`_ which analyze video
and audio streams and inject per-frame results into frame metadata to be used in a later stage of 
a filtergraph. :py:mod:`run` retrieves the injected metadata by appending ``metadata``
and ``ametadata`` filters and logs the frame metadata outputs. You can use either the supplied Python 
classes or a custom class, which conforms to :py:class:`MetadataLogger` interface to specify the FFmpeg
filter and to log its output.

---------------
Simple examples
---------------

The following example detects intervals of pure black frames within the first 30 seconds of the video:

>>> from ffmpegio import analyze as ffa
>>> logger, *_ = ffa.run("input.mp4", ffa.BlackDetect(pix_th=0.0), t=30) 
>>> print(logger.output)
Black(interval=[[0.0, 0.166667]])

* Assign options (e.g., ``pix_th``) of the underlying FFmpeg analysis filter (e.g., ``blackdetect``) as
  keyword options of its logger object (e.g., ``BlackDetect``)
* FFmpeg input options (e.g., ``t``) can be assigned as the keyword arguments of :py:func:`run`.
* The logger output is a namedtuple.

Next example analyzes the audio stream and plot its spectral entropy of the first channel:

>>> logger,*_ = ffa.run("input.mp4", ffa.ASpectralStats(measure='entropy'))
>>> plt.plot(logger.output.time, logger.output.entropy[0])

Finally, multiple loggers can run simultaneously:

>>> loggers = [
...   ffa.AStats(),       # time domain statistics of audio channels
...   ffa.BBox(),         # bounding box of video frames
...   ffa.BlackDetect()]  # detect black frame intervals
...
>>> ffa.run("input.mp4", *loggers, t=10)
>>> print(loggers[0].output)
>>> print(loggers[1].output)
>>> print(loggers[2].output)

------------------------
Available filter loggers
------------------------

Following loggers are currently available as a part of the :py:mod:`analyze` module

=====  ==========================  =================  ===
Type   Python class                FFmpeg filter      Description
=====  ==========================  =================  ===
audio  :py:class:`APhaseMeter`     `aphasemeter`_     Measures phase of input audio 
\      :py:class:`ASpectralStats`  `aspectralstats`_  Frequency domain statistical information
\      :py:class:`AStats`          `astats`_          Time domain statistical information 
\      :py:class:`SilenceDetect`   `silencedetect`_   Detect silence
video  :py:class:`BBox`            `bbox`_            Compute the bounding box
\      :py:class:`BlackDetect`     `blackdetect`_     Detect intervals of black frames
\      :py:class:`BlackFrame`      `blackframe`_      Detect black frames
\      :py:class:`BlurDetect`      `blurdetect`_      Detect blurriness of frames 
\      :py:class:`FreezeDetect`    `freezedetect`_    Detect frozen video
.. \      :py:class:`PSNR`            `psnr`_            Compute peak signal to noise ratio
\      :py:class:`ScDet`           `scdet`_           Detect video scene change
=====  ==========================  =================  ===

.. _aphasemeter: https://ffmpeg.org/ffmpeg-filters.html#aphasemeter
.. _aspectralstats: https://ffmpeg.org/ffmpeg-filters.html#aspectralstats
.. _astats: https://ffmpeg.org/ffmpeg-filters.html#astats-1
.. _silencedetect: https://ffmpeg.org/ffmpeg-filters.html#silencedetect
.. _bbox: https://ffmpeg.org/ffmpeg-filters.html#bbox
.. _blackdetect: https://ffmpeg.org/ffmpeg-filters.html#blackdetect
.. _blackframe: https://ffmpeg.org/ffmpeg-filters.html#blackframe
.. _blurdetect: https://ffmpeg.org/ffmpeg-filters.html#blurdetect-1
.. _freezedetect: https://ffmpeg.org/ffmpeg-filters.html#freezedetect
.. _psnr: https://ffmpeg.org/ffmpeg-filters.html#psnr
.. _scdet: https://ffmpeg.org/ffmpeg-filters.html#scdet-1

---------------------
Analyze API Reference
---------------------

.. autosummary::
   :nosignatures:
   :recursive:

   run
   ffmpegio.video.detect
   ffmpegio.audio.detect
   MetadataLogger

.. autofunction:: ffmpegio.analyze.run
.. autofunction:: ffmpegio.video.detect
.. autofunction:: ffmpegio.audio.detect
.. autoclass:: MetadataLogger
  :members:
.. autoclass:: APhaseMeter
  :members:
.. autoclass:: ASpectralStats
  :members:
.. autoclass:: AStats
  :members:
.. autoclass:: SilenceDetect
  :members:
.. autoclass:: BBox
  :members:
.. autoclass:: BlackDetect
  :members:
.. autoclass:: BlackFrame
  :members:
.. autoclass:: BlurDetect
  :members:
.. autoclass:: FreezeDetect
  :members:
.. .. autoclass:: PSNR
..   :members:
.. autoclass:: ScDet
  :members:
