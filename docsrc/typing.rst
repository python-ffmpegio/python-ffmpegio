.. py:module:`ffmpegio.typing`

.. _typing:

Typing (``ffmpegio.typing``)
============================

.. py:type:: ffmpegio.typing.RawDataBlob
    :canonical: Any

    Python object representing media data frame.

    A :py:type:`RawDataBlob` must contain the shape and data format of the media data as well as the binary data.
    Any data frame format could be used if user provides a custom data I/O plugin for it. 
    The table below lists the natively supported data object types (each enabled by one of built-in plugins):

    =========================================================================================================== =========================================
    Raw Data Blob Object Type                                                                                   Plugin                                   
    =========================================================================================================== =========================================
    :py:class:`ffmpegio.typing.BytesRawDataBlob`                                                                :py:mod:`ffmpegio.plugins.rawdata_bytes`
    :py:type:`numpy.typing.ArrayLike`                                                                           :py:mod:`ffmpegio.plugins.rawdata_numpy`
    :py:class:`matplotlib.figure.Figure`                                                                        :py:mod:`ffmpegio.plugins.rawdata_mpl`
    :py:class:`PIL.Image.Image` | :py:class:`PIL.ImageSequence.Iterator` | :py:type:`Sequence[PIL.Image.Image]` :py:mod:`ffmpegio.plugins.rawdata_pillow`
    =========================================================================================================== =========================================

.. autoclass:: ffmpegio.typing.BytesRawDataBlob
    :show-inheritance:

    .. autoproperty:: buffer
        :no-index:

.. py:type:: ffmpegio.typing.DTypeString
    :canonical: LiteralString

    Numpy array interface protocol typestr string

    The string format consists of 3 parts: a character describing the byteorder of the data 
    (:code:`'<'`: little-endian, :code:`'>'`: big-endian, :code:`'|'`: not-relevant), a character code giving 
    the basic type of the array, and an integer providing the number of bytes the type uses.

    Three basic type character codes are relevant to :py:mod:`ffmpegio` package:

    =========== ================
    code        description
    =========== ================
    :code:`'i'` Integer
    :code:`'u'` Unsigned integer
    :code:`'f'` Floating point
    =========== ================
    
    See https://numpy.org/doc/stable/reference/arrays.interface.html for Numpy's
    official documentation.

.. py:type:: ffmpegio.typing.ShapeTuple
    :canonical: tuple[int, ...]

    Tuple whose elements are the array size in each dimension. Each entry is an integer (a Python int).
    A video frame typically has 2 to 4 entries: :code:`([time, ]height, width[, color])`. 
    An audio frame has either 1 or 2 entries: :code:`(time[, channel])`. 

.. py:type:: ffmpegio.typing.FFmpegMediaType
    :canonical: Literal["video", "audio", "subtitle", "data", "attachments"]

    FFmpeg media stream types

    ===================== ==================
    value                 description
    ===================== ==================
    :code:`'video'`       video stream
    :code:`'audio'`       audio stream
    :code:`'subtitle'`    subtitle stream
    :code:`'data'`        data stream
    :code:`'attachments'` attachments stream
    ===================== ==================

.. py:type:: ffmpegio.typing.MediaType
    :canonical: Literal["audio", "video"]

    A subset of :py:type:`FFmpegMediaType` which is supported by :py:mod:`ffmpegio`

    =============== ============
    value           description
    =============== ============
    :code:`'video'` video stream
    :code:`'audio'` audio stream
    =============== ============


.. py:type:: ffmpegio.typing.FFmpegOptionDict
    :canonical: dict[str, Any]
    
    A dict that hold FFmpeg option name-value pairs

.. py:type:: ffmpegio.typing.RawStreamDef
.. py:type:: ffmpegio.typing.RawStreamInfoTuple
.. py:type:: ffmpegio.typing.ProgressCallable
    :canonical: Callable[[dict,bool], bool]

    FFmpeg progress callback function

    .. code::python

        callback(status, done)

    status - dict of encoding status
    done - True if the last callback

    The callback may return True to cancel the FFmpeg execution.


.. py:type:: ffmpegio.typing.FFmpegUrlType
.. py:type:: ffmpegio.typing.FFmpegInputType
.. py:type:: ffmpegio.typing.FFmpegOutputType
.. py:type:: ffmpegio.typing.GetInfoCallable
.. py:type:: ffmpegio.typing.ToBytesCallable
.. py:type:: ffmpegio.typing.CountDataCallable
.. py:type:: ffmpegio.typing.FromBytesCallable
.. py:type:: ffmpegio.typing.IsEmptyCallable
.. py:type:: ffmpegio.typing.RawInputInfoDict
.. py:type:: ffmpegio.typing.UrlEncodedInputInfoDict
.. py:type:: ffmpegio.typing.PipedEncodedInputInfoDict
.. py:type:: ffmpegio.typing.FileObjEncodedInputInfoDict
.. py:type:: ffmpegio.typing.EncodedInputInfoDict
.. py:type:: ffmpegio.typing.InputInfoDict
.. py:type:: ffmpegio.typing.PipeWriter
.. py:type:: ffmpegio.typing.PipeReader
.. py:type:: ffmpegio.typing.InputPipeInfoDict
.. py:type:: ffmpegio.typing.RawDirectOutputInfoDict
.. py:type:: ffmpegio.typing.RawFilteredOutputInfoDict
.. py:type:: ffmpegio.typing.RawOutputInfoDict
.. py:type:: ffmpegio.typing.UrlOrPipedEncodedOutputInfoDict
.. py:type:: ffmpegio.typing.FileObjEncodedOutputInfoDict
.. py:type:: ffmpegio.typing.EncodedOutputInfoDict
.. py:type:: ffmpegio.typing.OutputInfoDict
.. py:type:: ffmpegio.typing.OutputPipeInfoDict
.. py:type:: ffmpegio.typing.AudioFilterGraphInfoDict
.. py:type:: ffmpegio.typing.VideoFilterGraphInfoDict
.. py:type:: ffmpegio.typing.FilterGraphInfoDict
.. py:type:: ffmpegio.typing.FFmpegArgs 
.. py:type:: ffmpegio.typing.FilterGraphObject
.. py:type:: ffmpegio.typing.StreamSpecDict
.. py:type:: ffmpegio.typing.StreamSpecStreamType

