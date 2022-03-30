.. highlight:: python
.. _devices:

Hardware I/O Device Enumeration
===============================

FFmpeg supports `a number of hardware I/O devices <https://ffmpeg.org/ffmpeg-devices.html>`__, 
from which video or audio data are read (sources) and to which data are written (sinks).
For each device, which is specified via `-f` option, some of device hardware name
must be obtained via FFmpeg commands:

.. code-block:: bash

   ffmpeg -sources
   ffmpeg -sinks

If devices do not support these newer interfaces, via device-specific listing commands such as

.. code-block:: bash

   ffmpeg -f dshow -list_devices true -i dummy
   ffmpeg -f avfoundation -list_devices true -i ""

Moreover, some devices provide a query interface for the capability of individual hardware: 

.. code-block:: bash

   ffmpeg -list_options true -f dshow -i video="Camera"
   ffplay -f video4linux2 -list_formats all /dev/video0

For multi-hardware use, the hardware configuration must be scanned and chosen for each computer
even within a same OS. :py:mod:`ffmpegio.devices` module is intended to abstract the hardware
selection process via unified naming scheme following the stream specifiers. Device supports
are implemented via plugin module, so user can implement interface for unsupported devices. 

.. note::

   Currently, only Windows DirectShow source device (`-f dshow`) is supported. Developing
   device plugins, especially those on MacOS, requires user feedback and involvement. If
   you want a specific device to be supported, please post 
   `an issue on GitHub <https://github.com/python-ffmpegio/python-ffmpegio/issues>`__
   to initiate the process.


References
----------

.. autosummary::
   :nosignatures:
   :recursive:

   ffmpegio.devices.scan
   ffmpegio.devices.list_sources
   ffmpegio.devices.list_sinks
   ffmpegio.devices.list_source_options
   ffmpegio.devices.list_sink_options
   ffmpegio.devices.resolve_source
   ffmpegio.devices.resolve_sink

.. autofunction:: ffmpegio.devices.scan
.. autofunction:: ffmpegio.devices.list_sources
.. autofunction:: ffmpegio.devices.list_sinks
.. autofunction:: ffmpegio.devices.list_source_options
.. autofunction:: ffmpegio.devices.list_sink_options
.. autofunction:: ffmpegio.devices.resolve_source
.. autofunction:: ffmpegio.devices.resolve_sink
