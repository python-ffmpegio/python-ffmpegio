.. _probe:

Media Probe Function References
===============================

| PyPi: `<https://pypi.org/project/ffmpegio/>`__
| GitHub: `<https://github.com/python-ffmpegio/python-ffmpegio>`__


.. warning::
   This package is still in an early alpha stage and under heavy consturction.

:py:mod:`ffmpegio.probe` module contains a full-featured ffprobe wrapper function
:py:func:`ffmpegio.probe.full_details` and its derivative functions, which are
tailored to retrieve specific type of information from a media file or stream.

List of Functions
-----------------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.probe.format_basic
   ffmpegio.probe.streams_basic
   ffmpegio.probe.video_streams_basic
   ffmpegio.probe.audio_streams_basic
   ffmpegio.probe.full_details
   ffmpegio.probe.query

Function References
-------------------

.. autofunction:: ffmpegio.probe.format_basic
.. autofunction:: ffmpegio.probe.streams_basic
.. autofunction:: ffmpegio.probe.video_streams_basic
.. autofunction:: ffmpegio.probe.audio_streams_basic
.. autofunction:: ffmpegio.probe.full_details
.. autofunction:: ffmpegio.probe.query
