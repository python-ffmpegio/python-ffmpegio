.. py:module:: ffmpegio.typing
.. highlight:: python

.. _typing:

Typing (:code:`ffmpegio.typing`)
================================

Overview
--------

Referrences
-----------

.. py:type:: FFmpegUrlString
    :canonical: Any

    input and output file path or stream url str or stringifiable object.

.. py:type:: FFmpegInputUrlComposite
    :canonical: FFmpegUrlString | FFConcat | FilterGraphObject | IO | memoryview

    all input types supported by ffmpegio

.. py:type:: FFmpegOutputUrlComposite
    :canonical: FFmpegUrlString | IO

    all output types supported by ffmpegio

.. py:type:: FFmpegInputUrlNoPipe
    :canonical: FFmpegUrlString | FFConcat | FilterGraphObject

    all non-piped input types supported by ffmpegio

.. py:type:: FFmpegOutputUrlNoPipe
    :canonical: FFmpegUrlString

    all non-piped output types supported by ffmpegio


.. py:type:: FFmpegInputOptionTuple 
    :canonical: tuple[FFmpegInputUrlComposite, FFmpegOptionDict]

    tuple pair of FFmpeg input url compatible objects and its option dict

    Supported input url objects:

    - `str`
    - `os.Path`
    - `urllib.UrlParseResult`
    - `FFConcat`
    - `FilterGraphObject`
    - `IO` 
    - `Buffer`

.. py:type:: FFmpegOutputOptionTuple
    :canonical: tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]

    tuple pair of FFmpeg output url compatible objects and its option dict

    Supported output url objects:

    - `str`
    - `IO`
    - `Buffer`

.. py:type:: FFmpegNoPipeInputOptionTuple 
    :canonical: tuple[FFmpegInputUrlNoPipe, FFmpegOptionDict]

    tuple pair of FFmpeg input non-pipe url compatible objects and its option dict

    Supported input url objects:

    - `str`
    - `FFConcat`
    - `FilterGraphObject`

.. py:type:: FFmpegNoPipeOutputOptionTuple 
    :canonical: tuple[FFmpegOutputUrlNoPipe, FFmpegOptionDict]

    tuple pair of FFmpeg output non-pipe url compatible objects and its option dict


.. py:type:: RawDataBlob
    :canonical: Any

    Python object representing media data frame.

    A :py:type:`RawDataBlob` must contain the shape and data format of the media data as well as the binary data.
    Any data frame format could be used if user provides a custom data I/O plugin for it. 
    The table below lists the natively supported data object types (each enabled by one of built-in plugins):

    =========================================================================================================== =========================================
    Raw Data Blob Object Type                                                                                   Plugin                                   
    =========================================================================================================== =========================================
    :py:class:`BytesRawDataBlob`                                                                                :code:`ffmpegio.plugins.rawdata_bytes`
    :py:type:`numpy.typing.ArrayLike`                                                                           :code:`ffmpegio.plugins.rawdata_numpy`
    :py:class:`matplotlib.figure.Figure`                                                                        :code:`ffmpegio.plugins.rawdata_mpl`
    :py:class:`PIL.Image.Image` | :py:class:`PIL.ImageSequence.Iterator` | :code:`Sequence[PIL.Image.Image]`    :code:`ffmpegio.plugins.rawdata_pillow`
    =========================================================================================================== =========================================

.. autoclass:: BytesRawDataBlob
    :members:
    :undoc-members:    

.. py:type:: DTypeString
    :canonical: LiteralString

    Numpy array interface protocol typestr string

    The string format consists of 3 parts: a character describing the byteorder of the data 
    (:code:`'<'`: little-endian, :code:`'>'`: big-endian, :code:`'|'`: not-relevant), a character code giving 
    the basic type of the array, and an integer providing the number of bytes the type uses.

    Three basic type character codes are relevant to :code:`ffmpegio` package:

    =========== ================
    code        description
    =========== ================
    :code:`'i'` Integer
    :code:`'u'` Unsigned integer
    :code:`'f'` Floating point
    =========== ================
    
    See https://numpy.org/doc/stable/reference/arrays.interface.html for Numpy's
    official documentation.

.. py:type:: ShapeTuple
    :canonical: tuple[int, ...]

    Tuple whose elements are the array size in each dimension. Each entry is an integer (a Python int).
    A video frame typically has 2 to 4 entries: :code:`([time, ]height, width[, color])`. 
    An audio frame has either 1 or 2 entries: :code:`(time[, channel])`. 

.. py:type:: MediaType
    :canonical: Literal["audio", "video"]

    A subset of :py:type:`FFmpegMediaType` which is supported by :code:`ffmpegio`

    =============== ============
    value           description
    =============== ============
    :code:`'video'` video stream
    :code:`'audio'` audio stream
    =============== ============

.. py:type:: StreamSpecString
    :canonical: str

    An FFmpeg stream specifier is a string generally appended to the option name and separated from
    it by a colon. Possible forms of stream specifiers are:

    .. code-block:: bash

        stream_index
        stream_type[:additional_stream_specifier]
        g:group_specifier[:additional_stream_specifier]
        p:program_id[:additional_stream_specifier]
        #stream_id or i:stream_id
        m:key[:value]
        disp:dispositions[:additional_stream_specifier]
        u
    
    .. seealso:: https://ffmpeg.org/ffmpeg.html#Stream-specifiers

.. py:type:: StreamSpecDict
    :canonical: StreamSpecDict_Index | StreamSpecDict_Tag | StreamSpecDict_Usable | StreamSpecDict_Options

    :py:type:`StreamSpecString` organized as a Python dict. It takes one of the four forms:

    .. autoclass:: StreamSpecDict_Options
        :members:
        :undoc-members:    

    .. autoclass:: StreamSpecDict_Index
        :members:
        :undoc-members:    

    .. autoclass:: StreamSpecDict_Tag
        :members:
        :undoc-members:    

    .. autoclass:: StreamSpecDict_Usable
        :members:
        :undoc-members:    

.. py:type:: MapOptionString
    :canonical: str

    FFmpeg's :code:`-map` option specifies which input stream or filtergraph output is mapped to 
    an output media container or to return to Python with specific syntax
    
    .. code-block:: bash

        [-]input_file_id[:stream_specifier][:view_specifier][:?] | [linklabel]
    
.. py:type:: MapOptionDict 
    :canonical: InputMapOptionDict | GraphMapOptionDict

    Parsed dict of FFmpeg -map option string. Two possible forms:
        
    .. autoclass:: InputMapOptionDict
        :members:
        :undoc-members:    

    .. autoclass:: GraphMapOptionDict
        :members:
        :undoc-members:    

.. py:type:: ProgressCallable
    :canonical: Callable[[dict,bool], bool]

    FFmpeg progress callback function

    .. code::python

        callback(status, done)

    status - dict of encoding status
    done - True if the last callback

    The callback may return True to cancel the FFmpeg execution.

.. autoclass:: FFmpegArgs
    :members:
    :undoc-members:    

.. py:type:: FFmpegOptionDict
    :canonical: dict[str, Any]

    dict that hold FFmpeg option name-value pairs

    FFmpeg options with their values keyed by the option names without preceding dash (:code:`-`). 
    Option values may be of any Python data types, but they will be stringified when 
    they are converted to FFmpeg command arguments. For option flags (e.g., :code:`-y``) 
    without any value, use :code:`None` or its alias :code:`ffmpegio.FLAG`.

    For example,

    .. code-block:: bash

        ffmpeg -i input.mp4 -ss 00:01:30 -t 30 -an -c:v copy output.mp4

    specify 4 output options (:code:`-ss`, :code:`-t`, :code:`-an`, and :code:`-c:v`).
    These options can be specified by:

    .. code-block:: python

        output_opts = {"ss": "00:01:30", "t": 30, "an": ffmpegio.FLAG, "c:v": :copy"}

.. py:type:: FFmpegMediaType
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

