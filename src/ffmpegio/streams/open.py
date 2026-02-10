from __future__ import annotations

"""Open a multimedia file/stream for read/write

:param url_fg: URL of the media source/destination for file read/write or filtergraph definition
                for filter operation.
:type url_fg: str or seq(str)
:param mode: specifies the mode in which the FFmpeg is used, see below
:type mode: str

Start FFmpeg and open I/O link to it to perform read/write/filter operation and return
a corresponding stream object. If the file cannot be opened, an error is raised.
See :ref:`quick-streamio` for more examples of how to use this function.

Just like built-in `open()`, it is good practice to use the with keyword when dealing with
ffmpegio stream objects. The advantage is that the ffmpeg process and associated threads are
properly closed after ffmpeg terminates, even if an exception is raised at some point.
Using with is also much shorter than writing equivalent try-finally blocks.

:Examples:

Open an MP4 file and process all the frames::

    with ffmpegio.open('video_source.mp4', 'rv') as f:
        frame = f.read()
        while frame:
            # process the captured frame data
            frame = f.read()

Read an audio stream of MP4 file and write it to a FLAC file as samples
are decoded::

    with ffmpegio.open('video_source.mp4','ra') as rd:
        fs = rd.sample_rate
        with ffmpegio.open('video_dst.flac','wa',input_rate=fs) as wr:
            frame = rd.read()
            while frame:
                wr.write(frame)
                frame = rd.read()

:Additional Notes:

`urls_fgs` can be a string specifying either the path name (absolute or relative to the current
working directory) of the media target (file or streaming media) to be opened or a string describing
the filtergraph to be implemented. Its interpretation depends on the `mode` argument.

`mode` is an optional string that specifies the mode in which the FFmpeg is opened.

====  =======================================================
Mode  Description
====  =======================================================
'r'   read from encoded url/file/stream
'w'   write to encoded url/file/stream
'f'   filter data defined by fg
't'   transcode data
'->'  I/O operator
'v'   operate on video stream, 'vv' if multiple video streams
'a'   operate on audio stream, 'aa' if multiple audio streams
'e'   encoded data stream, 'ee' if multiple encoded streams
====  =======================================================

Each mode string is has one and only one operation specifier
(`'r'`, `'w'`, `'f'`, `'t'`, or `'->'`). For the operators `'rwf'`, accompany
them with a combination of the media specifiers `'v'` and `'a'` (repeated as
necessary). For the `'r'` operation, media specifiers specify the output
streams while they specify the input streams for `'w'` and `'f'`.

"""

"""`open()` module

`rate` and `input_rate`: Video frame rates shall be given in frames/second and
may be given as a number, string, or `fractions.Fraction`. Audio sample rate in
samples/second (per channel) and shall be given as an integer or string.

Optional `shape` or `input_shape` for video defines the video frame size and
number of components with a 2 or 3 element sequence: `(width, height[, ncomp])`.
The number of components and other optional `dtype` (or `input_dtype`) implicitly
define the pixel format (FFmpeg pix_fmt option):

=====  =====  =========  ===================================
ncomp  dtype  pix_fmt    Description
=====  =====  =========  ===================================
    1     \|u8   gray       grayscale
    1     <u2   gray10le   10-bit grayscale
    1     <u2   gray12le   12-bit grayscale
    1     <u2   gray14le   14-bit grayscale
    1     <u2   gray16le   16-bit grayscale (default <u2 choice)
    1     <f4   grayf32le  floating-point grayscale
    2     \|u1   ya8        grayscale with alpha channel
    2     <u2   ya16le     16-bit grayscale with alpha channel
    3     \|u1   rgb24      RGB
    3     <u2   rgb48le    16-bit RGB
    4     \|u1   rgba       RGB with alpha transparency channel
    4     <u2   rgba64le   16-bit RGB with alpha channel
=====  =====  =========  ===================================

For audio stream, single-element seq argument, `shape` or `input_shape`,
specifies the number of channels while `dtype` and `input_dtype` determines
the sample format (FFmpeg sample_fmt option):

======  ==========
dtype   sample_fmt
======  ==========
    \|u1     u8
    <i2     s16
    <i4     s32
    <f4     flt
    <f8     dbl
======  ==========

If dtypes and shapes are not specified at the time of opening, they will
be set during the first write/filter operation using the input data.

In addition, `open()` accepts the standard FFmpeg option keyword arguments.
"""


import logging
import re
from fractions import Fraction
from typing import overload

from .. import utils
from .._typing import (
    DTypeString,
    FFmpegOptionDict,
    Literal,
    LiteralString,
    ProgressCallable,
    Sequence,
    ShapeTuple,
    Unpack,
)
from ..configure import (
    FFmpegInputOptionTuple,
    FFmpegInputUrlComposite,
    FFmpegNoPipeOutputOptionTuple,
    FFmpegOutputOptionTuple,
    FFmpegOutputUrlComposite,
    FFmpegOutputUrlNoPipe,
)
from ..filtergraph.abc import FilterGraphObject
from .BaseFFmpegRunner import PipedFFmpegRunner, SISOFFmpegFilter, StdFFmpegRunner

logger = logging.getLogger("ffmpegio")

MapString = LiteralString
"""ffmpeg map option value"""

MultiReaderModeLiteral = LiteralString
"""multiple-output reader mode

To specify reading all media streams or multiple-streams, use

=============== =========================
mode (regexp)   description
=============== =========================
``'r'``         read all streams
``'r[va]{2,}'`` read more than one stream
=============== =========================

For example, ``'rvaa'`` produces three raw streams, video, audio, and audio
"""

MultiWriterModeLiteral = LiteralString
"""multiple-input writer mode

To specify writing multiple media streams, use

=============== ==========================
mode (regexp)   description
=============== ==========================
``'w[va]{2,}'`` write more than one stream
=============== ==========================

For example, ``'wvva'`` takes three raw streams, video, video, and audio

"""

MIMOFilterModeLiteral = LiteralString
"""multiple-input, multiple-output filter mode

To specify MIMO filter

========================= ================================================
mode (regexp)             description
========================= ================================================
``'f'``                   according to input and output filtergraph labels
``'f[va]{2,}'``           specify the input media types
``'[va]{2,}-\>[va]{2,}'`` specify the input and output media types
========================= ================================================
"""

DecoderModeLiteral = LiteralString
"""decoder mode

To configure FFmpeg as a decoder (encoded input, raw output), use

================ =================================
mode (regexp)    description
================ =================================
``'e+-\>[va]+'`` repeat ``'e'`` if multiple inputs
================ =================================

For example, ``'ee->vva'`` takes 2 encoded input streams and produces 3 raw 
media output streams (video, video, audio)
"""

EncoderModeLiteral = LiteralString
"""encoder mode

To configure FFmpeg as an encoder (raw input, encoded output), use

================ ==================================
mode (regexp)    description
================ ==================================
``'[va]+-\>e+'`` repeat ``'e'`` if multiple outputs
================ ==================================

For example, ``'vva->ee'`` takes 2 3 raw media output streams (video, video, 
audio) and produces encoded input streams
"""

TranscoderModeLiteral = LiteralString
"""transcoder mode

To specify FFmpeg to transcode, use

============= =========================================
mode (regexp) description
============= =========================================
``'e+-\>e+'`` repeat ``'e'`` if multiple inputs/outputs
============= =========================================
"""

MultiReaderModeLiteral = LiteralString
"""multiple-output reader mode

To specify reading all media streams or multiple-streams, use

============== =========================
mode (regexp)  description
============== =========================
``'r'``        read all streams
``'r[va]{2}'`` read more than one stream
============== =========================
"""


@overload
def open(
    urls_fgs: FFmpegInputUrlComposite
    | FFmpegInputOptionTuple
    | Sequence[FFmpegInputUrlComposite | FFmpegInputOptionTuple],
    mode: Literal["rv", "ra"],
    /,
    *,
    map: str | None = None,
    squeeze: bool = False,
    extra_outputs: Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple]
    | None = None,
    blocksize: int | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> StdFFmpegRunner:
    """open a single-stream reader

    :param urls_fgs: Specify encoded input file(s)/devices/filters in one of the
        following styles:

            - an input file url or other input stream/device supported by FFmpeg
            - a Python readable file object
            - an ``ffmpegio`` input format/device class object
              (e.g., ``FFConcat``)
            - an FFmpeg input filtergraph expression or
              ``ffmpegio.FilterGraphObject``
            - a pair of the url/filtergraph and a dict of FFmpeg input options
            - a sequence of the urls/filtergraphs or the pairs, or a mixture
              thereof. Use multiple inputs only to supply the data to a complex
              filtergraph combining multiple streams into one.

    :param urls_fgs: URL string of the file or format/device object. It can be
        an input filtergraph object or other input ffmpegio objects. The input
        could also be fed by a readable file object. Multiple input sources
        could also be assigned to feed a complex filtergraph.
    :param mode: ``'rv'`` to read video data or ``'ra'`` to read audio
    :param map: FFmpeg map output option, defaults to ``"0:v:0"`` for video and
        ``"0:a:0"`` for audio. The map option is required if ``options``
        contains the ``filter_complex`` option.
    :param squeeze: ``True`` (default) to eliminate raw output's singleton
        dimensions. Use ``False`` to always return 2D array for audio and 4D
        array for video.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param blocksize: Read block size (in frames for video or samples in audio)
        when the reader object is used as an iterator
    :param progress: progress callback function, defaults to ``None``
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: optional FFmpeg options including input, output, and
        global options. For input options, append ``'_in'`` to the end of
        FFmpeg option names.
    :return: a reader stream object
    """


@overload
def open(
    urls_fgs: FFmpegOutputUrlNoPipe
    | FFmpegNoPipeOutputOptionTuple
    | list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple],
    mode: Literal["wv", "wa"],
    /,
    input_rate: int | Fraction,
    *,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    input_shape: ShapeTuple | None = None,
    input_dtype: DTypeString | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    overwrite: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> StdFFmpegRunner:
    """open a single-stream media writer

    :param urls_fgs: Specify encoded output file(s) in one of the following
        styles:

            - an output file url
            - a pair of an output url and a dict of FFmpeg output options
            - a sequence of the urls or the pairs or a mixture thereof. This
                commands FFmpeg to generate multiple files simultaneously from
                the same input streams.

    :param mode: ``'wv'`` to create a media file from a raw video stream or
        ``'wa'`` from a raw audio stream.
    :param input_rate: input frame rate in frames/second (video) or sampling
        rate in samples/second (audio)
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param input_shape: input video frame size (height, width) or number of
        input audio channel, defaults to auto-detect
    :param input_dtype: input data format in a Numpy dtype string, defaults to
        auto-detect
    :param progress: progress callback function, defaults to ``None``
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param overwrite: ``True`` to overwrite ``extra_outputs`` destination files,
        defaults to ``False``
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: optional FFmpeg options including input, output, and
        global options. For input options, append ``'_in'`` to the end of
        FFmpeg option names.
    :return: writer stream object

    """


@overload
def open(
    urls_fgs: str | FilterGraphObject | Literal["-"],
    mode: Literal["fv", "fa", "v->v", "a->a", "v->a", "a->v"],
    /,
    input_rate: int | Fraction,
    *,
    squeeze: bool = False,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: (
        list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
    ) = None,
    input_shape: ShapeTuple | None = None,
    input_dtype: DTypeString | None = None,
    blocksize: int | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> SISOFFmpegFilter:
    """open a single-input single-output media filter

    :param urls_fgs: Specify the filtergraph to be used with an FFmpeg
        filtergraph expression or an ``ffmpegio.FilterGraphObject`` object. Use
        ``'-'`` if the filtering is implicitly specified via output options
        (such as rate or format changes).
    :param mode: Specify the SISO filter mode by one of the following:

        - ``'fv'`` or ``'v->v'`` to take a video stream and produce a video stream
        - ``'fa'`` or ``'a->a'`` to take an audio stream and produce an audio stream
        - ``'v->a'`` to take a video stream and produce an audio stream
        - ``'a->v'`` to take an audio stream and produce a video stream

        Note that currently the output stream media types are not checked.
    :param input_rate: Input frame rate (video) or sampling rate (audio)
    :param squeeze: ``True`` (default) to eliminate raw output's singleton
        dimensions. Use ``False`` to always return 2D array for audio and 4D
        array for video.
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param input_shape: input video frame size (height, width) or number of
        input audio channels, defaults to None (auto-detect)
    :param input_dtype: input data format as a Numpy dtype string, defaults to
        None (auto-detect)
    :param blocksize: Read queue item size of the in frames for video or samples
        in audio Read block size. This size is also used when the reader object
        is used as an iterator.
    :param enc_blocksize: Queue item size of the extra encoded output stream
        in bytes, defaults to 64 MB (2**16 bytes).
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero  (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to ``None``
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: optional FFmpeg options including input, output, and
        global options. For input options, append ``'_in'`` to the end of
        FFmpeg option names.
    :return: audio writer stream object

    """


@overload
def open(
    urls_fgs: FFmpegInputUrlComposite
    | FFmpegInputOptionTuple
    | Sequence[FFmpegInputUrlComposite | FFmpegInputOptionTuple],
    mode: MultiReaderModeLiteral,
    /,
    *,
    output_streams: Sequence[MapString | FFmpegOptionDict] | None = None,
    squeeze: bool = False,
    extra_outputs: Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None,
    primary_output: int | None = None,
    blocksize: int | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a multi-stream reader

    :param urls_fgs: Specify encoded input file(s)/devices/filters in one of the
        following styles:

            - an input file url or other input stream/device supported by FFmpeg
            - a Python readable file object
            - an ``ffmpegio`` input format/device class object
              (e.g., ``FFConcat``)
            - an FFmpeg input filtergraph expression or
              ``ffmpegio.FilterGraphObject``
            - a pair of the url/filtergraph and a dict of FFmpeg input options
            - a sequence of the urls/filtergraphs or the pairs, or a mixture
              thereof.

    :param mode: Specify the multi-stream reader by one of the following:

        - ``'r'`` to include all the streams in the input urls or all the
          outputs of the complex filtergraphs.
        - ``'r'`` followed by a mixture of ``'v'`` and ``'a'`` to specify the
          number of streams to read and their media types, e.g., ``'rvva'``
          reads two video streams and an audio stream.

    :param output_streams: output stream options:

        - `None` to auto-select. If ``mode='r'`` then all input streams (or
          all filtergraph outputs) are selected. If ``mode`` specifies the
          number of streams, then the streams are selected in their stream
          indices if only one url is specified without any complex filtergraph.
        - a sequence of str to specify map output option
        - a sequence of output option dict with `'map'` item to output-specific
            options
        - a dict with map specifier or user keys to specify output options,
            again to specify output-specific options. The keys will be used
            as the keys of the raw data output, and can be different from
            the `'map'` option so long as the `'map'` option is given in the
            dict.

    :param squeeze: ``True`` (default) to eliminate raw output's singleton
        dimensions. Use ``False`` to always return 2D array for audio and 4D
        array for video.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param primary_output: Index of a raw media output stream which serves as
                           the reference frame to sync all output streams,
                           defaults to ``0``.
    :param blocksize: Read queue item size of the primary output stream in
        frames for video or samples in audio Read block size. This size is also
        used when the reader object is used as an iterator.
    :param enc_blocksize: Queue item size of the extra encoded output stream
        in bytes, defaults to 64 MB (2**16 bytes).
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero  (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to ``None``
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param overwrite: ``True`` to overwrite ``extra_outputs`` destination files,
        defaults to ``False``
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: optional FFmpeg options including input, output, and
        global options. For input options, append ``'_in'`` to the end of
        FFmpeg option names.
    :return: reader stream object
    """


@overload
def open(
    urls_fgs: FFmpegOutputUrlNoPipe
    | FFmpegNoPipeOutputOptionTuple
    | list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple],
    mode: MultiWriterModeLiteral,
    /,
    input_rates: list[int | Fraction],
    *,
    input_options: Sequence[FFmpegOptionDict] | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    input_shapes: Sequence[ShapeTuple] | None = None,
    input_dtypes: Sequence[DTypeString] | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    overwrite: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a multi-stream media writer

    :param urls_fgs: Specify encoded output file(s) in one of the following
        styles:

            - an output file url
            - a pair of an output url and a dict of FFmpeg output options
            - a sequence of the urls or the pairs or a mixture thereof. This
                commands FFmpeg to generate multiple files simultaneously from
                the same input streams.

    :param mode: Specify the multi-stream writer by one of the following:

        - ``'w'`` to set the input streams solely by ``input_options`` argument
        - ``'w'`` followed by a mixture of ``'v'`` and ``'a'`` to specify the
          number of streams to write and their media types, e.g., ``'wvva'``
          writes two video streams and an audio stream to the url.

    :param input_rates: list of input frame rates (video) and sampling rates
        (audio)
    :param input_options: Specify per-stream FFmpeg options of the raw input
        streams. These option values are added to the default input options
        specified in ``options``. If ``input_rates`` is not provided, the frame/
        sampling rate keys (i.e., ``'r'`` or ``'ar'``) must be present.
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param input_shapes: input video frame sizes (height, width) or a number of
        input audio channels, defaults to auto-detect. 'input_dtypes' must also
        be specified for this argument to be processed.
    :param input_dtypes: input data format as a Numpy dtype string, defaults to
        auto-detect. 'input_shapes' must also be specified for this argument to
        be processed.
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero  (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to ``None``
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param overwrite: ``True`` to overwrite ``extra_outputs`` destination files,
        defaults to ``False``
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: optional FFmpeg options including input, output, and
        global options. For input options, append ``'_in'`` to the end of
        FFmpeg option names.
    :return: writer stream object

    """


@overload
def open(
    urls_fgs: str | FilterGraphObject | list[str | FilterGraphObject] | Literal["-"],
    mode: MIMOFilterModeLiteral,
    /,
    input_rates: list[int | Fraction],
    *,
    input_options: Sequence[FFmpegOptionDict] | None = None,
    output_streams: Sequence[MapString | FFmpegOptionDict]
    | dict[str, MapString | FFmpegOptionDict]
    | None = None,
    squeeze: bool = False,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    input_shapes: list[ShapeTuple] | None = None,
    input_dtypes: list[DTypeString] | None = None,
    primary_output: int | None = None,
    blocksize: int | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """Open a multiple-input-multiple-output media filter

    :param urls_fgs: Specify the filtergraph to be used with an FFmpeg
        filtergraph expression or an ``ffmpegio.FilterGraphObject`` object. Use
        ``'-'`` if the filtering is implicitly specified via output options
        (such as rate or format changes). If multiple complex filtergraphs are
        needed, provide them as a list.
    :param mode: Specify MIMO filter mode by one of the following:

        - ``'f'`` to auto-detect the numbers of input and output streams
        - ``'f'`` followed by a mixture of ``'v'`` and ``'a'`` to specify the
          number of input streams and their media types, e.g., ``'fvva'``
          takes two video input streams and an audio input stream. The output
          stream is auto-detected.
        - an arrow notation (``'->'``) with its input and output each specified
          by a mixture of ``'v'`` and ``'a'``. For example, ``'vva->v'`` takes
          two video input streams and an audio input stream to produce one video
          stream. Note the output designators are currently not checked.

    :param input_rates: list of input frame rates (video) and sampling rates
        (audio)
    :param input_options: Specify per-stream FFmpeg options of the raw input
        streams. These option values are added to the default input options
        specified in ``options``. If ``input_rates`` is not provided, the frame/
        sampling rate keys (i.e., ``'r'`` or ``'ar'``) must be present.
    :param output_streams: output stream options:

        - `None` to auto-select. If ``mode='r'`` then all input streams (or
          all filtergraph outputs) are selected. If ``mode`` specifies the
          number of streams, then the streams are selected in their stream
          indices if only one url is specified without any complex filtergraph.
        - a sequence of str to specify map output option
        - a sequence of output option dict with `'map'` item to output-specific
            options
        - a dict with map specifier or user keys to specify output options,
            again to specify output-specific options. The keys will be used
            as the keys of the raw data output, and can be different from
            the `'map'` option so long as the `'map'` option is given in the
            dict.

    :param squeeze: ``True`` (default) to eliminate raw output's singleton
        dimensions. Use ``False`` to always return 2D array for audio and 4D
        array for video.
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param input_shapes: input video frame sizes (height, width) or a number of
        input audio channels, defaults to auto-detect. 'input_dtypes' must also
        be specified for this argument to be processed.
    :param input_dtypes: input data format as a Numpy dtype string, defaults to
        auto-detect. 'input_shapes' must also be specified for this argument to
        be processed.
    :param primary_output: Index of a raw media output stream which serves as
                           the reference frame to sync all output streams,
                           defaults to ``0``.
    :param blocksize: Read queue item size of the primary output stream in
        frames for video or samples in audio Read block size. This size is also
        used when the reader object is used as an iterator.
    :param enc_blocksize: Queue item size of the extra encoded output stream
        in bytes, defaults to 64 MB (2**16 bytes).
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero  (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to None
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: global/default FFmpeg options. For output and global options,
        use FFmpeg option names as is. For input options, append "_in" to the
        option name. For example, r_in=2000 to force the input frame rate
        to 2000 frames/s (see :doc:`options`). These input and output options
        specified here are treated as default, common options, and the
        url-specific duplicate options in the ``inputs`` or ``outputs``
        sequence will overwrite those specified here.
    :return: reader stream object
    """


@overload
def open(
    urls_fgs: Literal["-"],
    mode: DecoderModeLiteral,  # r"e+-\>[av]+",
    /,
    *,
    output_streams: Sequence[MapString | FFmpegOptionDict]
    | dict[str, MapString | FFmpegOptionDict]
    | None = None,
    squeeze: bool = False,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    primary_output: int | None = None,
    blocksize: int | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a media decoder (encoded streams in, raw streams out)

    :param urls_fgs: ``'-'`` to indicate pipe-in pipe-out operation
    :param mode: Specify the decoder mode by an arrow notation (``'->'``) with
        its input by a repeated ``'e'`` and output by a mixture of ``'v'`` and
        ``'a'``. For example, ``'ee->vva'`` takes two encoded media streams and
        produces two video output streams and an audio output stream.
    :param output_streams: output stream options:

        - `None` to auto-select. If ``mode='r'`` then all input streams (or
          all filtergraph outputs) are selected. If ``mode`` specifies the
          number of streams, then the streams are selected in their stream
          indices if only one url is specified without any complex filtergraph.
        - a sequence of str to specify map output option
        - a sequence of output option dict with `'map'` item to output-specific
            options
        - a dict with map specifier or user keys to specify output options,
            again to specify output-specific options. The keys will be used
            as the keys of the raw data output, and can be different from
            the `'map'` option so long as the `'map'` option is given in the
            dict.

    :param squeeze: ``True`` (default) to eliminate raw output's singleton
        dimensions. Use ``False`` to always return 2D array for audio and 4D
        array for video.
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param primary_output: Index of a raw media output stream which serves as
                           the reference frame to sync all output streams,
                           defaults to ``0``.
    :param blocksize: Read queue item size of the primary output stream in
        frames for video or samples in audio Read block size. This size is also
        used when the reader object is used as an iterator.
    :param enc_blocksize: Queue item size of the extra encoded output stream
        in bytes, defaults to 64 MB (2**16 bytes).
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to None
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param overwrite: ``True`` to overwrite ``extra_outputs`` destination files,
        defaults to ``False``
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: global/default FFmpeg options. For output and global options,
        use FFmpeg option names as is. For input options, append "_in" to the
        option name. For example, r_in=2000 to force the input frame rate
        to 2000 frames/s (see :doc:`options`). These input and output options
        specified here are treated as default, common options, and the
        url-specific duplicate options in the ``inputs`` or ``outputs``
        sequence will overwrite those specified here.
    :return: writer stream object

    """


@overload
def open(
    urls_fgs: Literal["-"],
    mode: EncoderModeLiteral,
    /,
    input_rates: list[int | Fraction],
    *,
    input_options: list[FFmpegOptionDict] | None = None,
    output_options: list[FFmpegOptionDict],
    extra_inputs: list[FFmpegInputOptionTuple] | None = None,
    extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
    input_shapes: list[ShapeTuple] | None = None,
    input_dtypes: list[DTypeString] | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: FFmpegOptionDict,
) -> PipedFFmpegRunner:
    """open a media encoder (raw streams in, encoded streams out)

    :param urls_fgs: ``'-'`` to indicate pipe-in pipe-out operation
    :param mode: Specify the encoder mode by an arrow notation (``'->'``) with
        its input by a mixture of ``'v'`` and ``'a'`` and output by a repeated
        ``'e'``. For example, ``'vva->ee'`` takes two video input streams and
        an audio input stream to produce two encoded media streams.
    :param input_rates: list of input frame rates (video) and sampling rates
        (audio)
    :param input_options: Specify per-stream FFmpeg options of the raw input
        streams. These option values are added to the default input options
        specified in ``options``. If ``input_rates`` is not provided, the frame/
        sampling rate keys (i.e., ``'r'`` or ``'ar'``) must be present.
    :param output_options: Specify per-stream FFmpeg options of the encoded
        output streams. These option values are added to the default output
        options specified in ``options``.
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param input_shapes: input video frame sizes (height, width) or a number of
        input audio channels, defaults to auto-detect. 'input_dtypes' must also
        be specified for this argument to be processed.
    :param input_dtypes: input data format as a Numpy dtype string, defaults to
        auto-detect. 'input_shapes' must also be specified for this argument to
        be processed.
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to None
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: global/default FFmpeg options. For output and global options,
                    use FFmpeg option names as is. For input options, append "_in" to the
                    option name. For example, r_in=2000 to force the input frame rate
                    to 2000 frames/s (see :doc:`options`). These input and output options
                    specified here are treated as default, common options, and the
                    url-specific duplicate options in the ``inputs`` or ``outputs``
                    sequence will overwrite those specified here.
    :return: writer stream object

    """


@overload
def open(
    urls_fgs: Literal["-"],
    mode: TranscoderModeLiteral,  # r"e+-\>e+",
    /,
    *,
    input_options: list[FFmpegOptionDict] | None = None,
    output_options: list[FFmpegOptionDict] | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a media transcoder (encoded streams in, encoded streams out)

    :param urls_fgs: ``'-'`` to indicate pipe-in pipe-out operation
    :param mode: Specify the transcoder mode by an arrow notation (``'->'``)
        with its inputs and outputs each by a repeated ``'e'``. For example,
        ``'e->ee'`` transcodes one encoded stream to two encoded streams.
    :param input_options: Specify per-stream FFmpeg options of the encoded input
        streams. These option values are added to the default input options
        specified in ``options``.
    :param output_options: Specify per-stream FFmpeg options of the encoded
        output streams. These option values are added to the default output
        options specified in ``options``.
    :param extra_inputs: extra encoded input urls, Each element is a tuple pair
        of url and input option dict. The url must be a url and not pipes or
        pipe objects.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
        pair of url and output option dict. The url must be a url and not
        pipes or pipe objects. Note: If output files will always be overwritten
        if they exist.
    :param enc_blocksize: Queue item size of the extra encoded output stream
        in bytes, defaults to 64 MB (2**16 bytes).
    :param queuesize: Background reader & writer threads queue size, defaults to
        16. Use zero (0) to specify unlimited queue size.
    :param timeout: Queue read timeout in seconds, defaults to ``None`` to
        wait indefinitely.
    :param progress: progress callback function, defaults to None
    :param show_log: ``True`` to show FFmpeg log messages on the console,
        defaults to ``False``, hiding the logged messages
    :param sp_kwargs: keyword dict to be passed to ``subprocess.run()`` or
        ``subprocess.Popen()`` call used to run the FFmpeg, defaults to ``None``
    :param options: global/default FFmpeg options. For output and global options,
        use FFmpeg option names as is. For input options, append "_in" to the
        option name. For example, r_in=2000 to force the input frame rate
        to 2000 frames/s (see :doc:`options`). These input and output options
        specified here are treated as default, common options, and the
        url-specific duplicate options in the ``inputs`` or ``outputs``
        sequence will overwrite those specified here.
    :return: writer stream object

    """


def open(
    urls_fgs,
    mode,
    /,
    *args,
    **kwargs,
) -> PipedFFmpegRunner | SISOFFmpegFilter | StdFFmpegRunner:

    # possible keywords, excluding FFmpeg options
    # 'input_shape', 'input_dtype', 'input_rate', 'input_rates',
    # 'input_options', 'input_dtypes', 'input_shapes', 'extra_inputs',
    # 'output_streams', 'extra_outputs', 'squeeze'

    op_mode, in_types, out_types = _parse_mode(mode)
    if urls_fgs == "-" and op_mode in "rw":
        raise ValueError(
            f"{'Input of a reader' if op_mode == 'r' else 'Output of a writer'} cannot be piped ('-'). Provide at least one URL."
        )

    runner_kws = {
        k: kwargs.pop(k)
        for k in (
            "input_shape",
            "input_dtype",
            "input_shapes",
            "input_dtypes",
            "primary_output",
            "blocksize",
            "enc_blocksize",
            "queuesize",
            "timeout",
            "progress",
            "show_log",
            "overwrite",
            "sp_kwargs",
        )
        if k in kwargs
    }

    if op_mode in "rdt" and len(args):
        raise TypeError(
            "Too many positional arguments. Only 2 positional arguments are allowed for reader/decoder/transcoder."
        )

    if op_mode == "r":
        runner = _open_reader(out_types, urls_fgs, kwargs, runner_kws)
    elif op_mode == "w":
        runner = _open_writer(in_types, urls_fgs, args, kwargs, runner_kws)
    elif op_mode == "f":
        runner = _open_filter(in_types, out_types, urls_fgs, args, kwargs, runner_kws)
    elif op_mode == "d":
        runner = _open_decoder(
            len(in_types), out_types, urls_fgs, args, kwargs, runner_kws
        )
    elif op_mode == "e":
        runner = _open_encoder(
            in_types, len(out_types), urls_fgs, args, kwargs, runner_kws
        )
    else:
        runner = _open_transcoder(
            len(in_types), len(out_types), urls_fgs, args, kwargs, runner_kws
        )

    return runner


def _parse_mode(mode: str) -> tuple[Literal["r", "w", "f", "d", "e", "t"], str, str]:
    """parse operating mode literal string

    :return op_mode: operating mode character
    :return input_types: input stream type sequence
    :return output_types: output stream type sequence
    """
    m = re.fullmatch(
        r"(t)|([av]*?)([rwfed])([av]*?)|((?:[av]+|e+))-\>((?:[av]+|e+))", mode
    )
    if m is None:
        raise ValueError(f"{mode=} is an invalid operation mode specifier")

    op_mode = m[1] or m[3]

    if op_mode is not None:
        inputs = m[2] or ""
        outputs = m[4] or ""
        if op_mode == "t":
            inputs = outputs = "e"
        elif op_mode in "efw":
            # writer & (single-output) decoder -> output media types
            inputs = inputs + outputs
            outputs = "e" if op_mode == "e" else ""
        else:
            # others -> input media types
            outputs = inputs + outputs
            inputs = "e" if op_mode == "d" else ""
    else:  # arrow convention
        inputs = m[5] or ""
        outputs = m[6] or ""
        in_encoded = all(c == "e" for c in inputs)
        out_encoded = all(c == "e" for c in outputs)
        op_mode = {
            (False, False): "f",
            (False, True): "e",
            (True, False): "d",
            (True, True): "t",
        }[(in_encoded, out_encoded)]

    return op_mode, inputs, outputs


def _open_kws_set() -> list[str]:
    return set(
        [
            "input_shape",
            "input_dtype",
            "input_rate",
            "input_rates",
            "input_options",
            "input_dtypes",
            "input_shapes",
            "extra_inputs",
            "output_streams",
            "extra_outputs",
            "squeeze",
        ]
    )


def _process_raw_input_args(
    in_types: str, args: tuple, kwargs: dict
) -> tuple[
    set[str],
    bool,
    list[FFmpegOptionDict],
    Sequence[str | tuple[str, FFmpegOptionDict]] | None,
]:
    """process raw input arguments

    :param in_types: input media type sequence
    :param args: positional arguments (3rd-)
    :param kwargs: keyword arguments
    :return used_kws: popped keyword arguments
    :return signel_input: True if only one input stream
    :return input_options: list of per-stream ffmpeg input options
    :return extra_inputs: keyword arguemnt to define extra inputs
    """
    nargs = len(args)
    if nargs > 1:
        raise TypeError(
            f"ffmpegio.open() takes two to three positional arguments ({2 + len(args)} given) to open a writer"
        )

    input_options = kwargs.pop("input_options", None)
    extra_inputs = kwargs.pop("extra_inputs", None)
    used_kws = {"extra_inputs"}
    single_input = len(in_types) == 1  #

    # establish input_options
    if single_input:
        input_rate = kwargs.pop("input_rate", None)
        used_kws.add("input_rate")
        if nargs:
            if input_rate is None:
                input_rate = args[0]
            else:
                raise TypeError("'input_rate' specified multiple times")

        rate_opt = {"ar" if in_types[0] == "a" else "r": input_rate}
        input_options = [
            rate_opt if input_options is None else {**input_options, **rate_opt}
        ]

    else:
        input_rates = kwargs.pop("input_rates", None)
        used_kws.add("input_rates")
        input_options = kwargs.pop("input_options", None)
        used_kws.add("input_options")

        if nargs:
            if input_rates is None:
                input_rates = args[0]
            else:
                raise TypeError("'input_rates' specified multiple times")

        if len(in_types) == 0:
            # expects input_options to define the rates
            if input_rates is not None and input_options is None:
                raise ValueError("Cannot resolve the input streams.")
        elif input_options is None:
            input_options = [
                {"ar" if mtype == "a" else "r": r}
                for mtype, r in zip(in_types, input_rates)
            ]
        else:
            input_options = [
                {**opts, "ar" if mtype == "a" else "r": r}
                for mtype, r, opts in zip(in_types, input_rates, input_options)
            ]

    return used_kws, single_input, input_options, extra_inputs


def _process_raw_output_args(
    out_types: Sequence[Literal["a", "v"]], kwargs: dict, nin: int
) -> tuple[
    set[str],
    bool,
    list[FFmpegOptionDict],
    Sequence[FFmpegOutputOptionTuple] | None,
    bool,
]:
    """process arguments for raw output options

    :param out_types: output media sequence
    :param kwargs: keyword arguments
    :param nin: number of input urls
    :return used_kws: set of keyword arguments consumed
    :return single_output: True if single output
    :return output_streams: ffmpeg output options
    :return extra_outputs: extra output urls (+options)
    :return squeeze: True to squeeze raw output blobs
    """
    nout = len(out_types)
    single_output = nout == 1  # single encoded stream

    output_streams = None
    extra_outputs = kwargs.pop("extra_outputs", None)
    squeeze = kwargs.pop("squeeze", None)

    used_kws = set(["extra_outputs", "squeeze"])
    if single_output:
        used_kws.add("output_streams")
    else:
        output_streams = kwargs.pop("output_streams", None)

    if isinstance(output_streams, (str, dict)):
        output_streams = [output_streams]

    if len(out_types) == 0:  # autodetect
        single_output = False  # -> multi-output
    else:
        # resolve the output streams
        nout = len(out_types)

        if output_streams is None:
            output_streams = [{} for _ in range(nout)]
        elif nout != len(output_streams):
            raise ValueError(
                "number of outputs in mode does not match the number of output options specified."
            )
        else:
            output_streams = [
                {**s} if isinstance(s, dict) else s for s in output_streams
            ]

        if (
            "map" not in kwargs
            and nin == 1
            and not utils.find_filter_complex_option(kwargs)
        ):
            stream_counts = {"a": 0, "v": 0}
            for mtype, opts in zip(out_types, output_streams):
                st = stream_counts[mtype]
                stream_counts[mtype] += 1

                if isinstance(opts, dict) and "map" not in opts:
                    opts["map"] = f"0:{mtype}:{st}"
    return used_kws, single_output, output_streams, extra_outputs, squeeze


def _open_reader(
    out_types: str,
    urls: FFmpegInputUrlComposite
    | FFmpegInputOptionTuple
    | Sequence[FFmpegInputUrlComposite | FFmpegInputOptionTuple],
    kwargs: dict,
    runner_kws: dict,
) -> StdFFmpegRunner | PipedFFmpegRunner:

    # need to resolve if multiple input urls are given
    urls = [urls] if utils.is_valid_input_url(urls) or isinstance(urls, tuple) else urls
    nin = len(urls)

    used_kws, single_output, output_streams, extra_outputs, squeeze = (
        _process_raw_output_args(out_types, kwargs, nin)
    )

    open_kws = _open_kws_set() - used_kws
    for k in open_kws:
        if k in kwargs:
            raise TypeError(f"Invalid keyword inputs found: {k}")

    if "overwrite" in runner_kws and runner_kws["overwrite"] is not None:
        raise TypeError("'overwrite' keyword is not supported in the reader mode.")

    return (
        StdFFmpegRunner.open_simple_reader(
            urls,
            output_streams[0],
            kwargs,
            squeeze,
            extra_outputs,
            **runner_kws,
        )
        if single_output
        else PipedFFmpegRunner.open_media_reader(
            urls, output_streams, kwargs, squeeze, extra_outputs, **runner_kws
        )
    )


def _open_writer(
    in_types: str,
    urls: FFmpegOutputUrlComposite
    | FFmpegOutputOptionTuple
    | Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner | StdFFmpegRunner:

    used_kws, single_input, input_options, extra_inputs = _process_raw_input_args(
        in_types, args, kwargs
    )

    open_kws = _open_kws_set() - used_kws
    for k in open_kws:
        if k in kwargs:
            raise TypeError(f"Invalid keyword inputs found: {k}")

    # insert default output mapping
    if "map" not in kwargs and utils.find_filter_complex_option(kwargs) is None:
        kwargs["map"] = [f"{i}:{mtype}:0" for i, mtype in enumerate(in_types)]

    return (
        StdFFmpegRunner.open_simple_writer(
            urls,
            input_options[0],
            kwargs,
            extra_inputs,
            **runner_kws,
        )
        if single_input
        else PipedFFmpegRunner.open_media_writer(
            urls,
            input_options,
            kwargs,
            extra_inputs,
            **runner_kws,
        )
    )


def _open_filter(
    in_types: str,
    out_types: str,
    fgs: str | FilterGraphObject | Sequence[str | FilterGraphObject] | None,
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> SISOFFmpegFilter:

    used_kws, single_input, input_options, extra_inputs = _process_raw_input_args(
        in_types, args, kwargs
    )
    open_kws = _open_kws_set() - used_kws

    used_kws, single_output, output_streams, extra_outputs, squeeze = (
        _process_raw_output_args(out_types, kwargs, len(in_types))
    )
    open_kws -= used_kws

    for k in open_kws:
        if k in kwargs:
            raise TypeError(f"Invalid keyword inputs found: {k}")

    if "overwrite" in runner_kws and runner_kws["overwrite"] is not None:
        raise TypeError("'overwrite' keyword is not supported in the filter mode.")

    single = single_input and (single_output or output_streams is None)

    if fgs is not None and fgs != "-":
        kwargs["filter_complex"] = fgs

    return (
        SISOFFmpegFilter.create_and_open(
            input_options[0],
            output_streams and output_streams[0],
            kwargs,
            squeeze,
            extra_inputs,
            extra_outputs,
            **runner_kws,
        )
        if single
        else PipedFFmpegRunner.open_media_filter(
            input_options,
            output_streams,
            kwargs,
            squeeze,
            extra_inputs,
            extra_outputs,
            **runner_kws,
        )
    )


def _open_decoder(
    nb_in: int,
    out_types: str,
    urls: Literal["-"],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner:

    if urls != "-":
        raise TypeError("urls_fgs argument for a decoder must be '-'.")

    if len(args):
        raise TypeError(
            "ffmpegio.open() does not take more than 2 positional arguments for a decoder."
        )

    used_kws, _, output_streams, extra_outputs, squeeze = _process_raw_output_args(
        out_types, kwargs, nb_in
    )
    open_kws = _open_kws_set() - used_kws

    input_options = kwargs.pop("input_options", None)

    if input_options is None:
        input_options = [{} for i in range(nb_in)]
    elif nb_in > 0 and len(input_options) != nb_in:
        raise ValueError(
            "the length of 'input_options' must match the number of encoded inputs"
        )
    extra_inputs = kwargs.pop("extra_inputs", None)

    open_kws -= {"input_options", "extra_inputs"}

    for k in open_kws:
        if k in kwargs:
            raise TypeError(f"Invalid keyword inputs found: {k}")

    if "overwrite" in runner_kws and runner_kws["overwrite"] is not None:
        raise TypeError("'overwrite' keyword is not supported in the decoder mode.")

    return PipedFFmpegRunner.open_media_decoder(
        input_options,
        output_streams,
        kwargs,
        squeeze,
        extra_inputs,
        extra_outputs,
        **runner_kws,
    )


def _open_encoder(
    in_types: str,
    nb_out: int,
    urls: Literal["-"],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner:

    if urls != "-":
        raise TypeError("urls_fgs argument for an encoder must be '-'.")

    used_kws, _, input_options, extra_inputs = _process_raw_input_args(
        in_types, args, kwargs
    )
    open_kws = _open_kws_set() - used_kws

    output_options = kwargs.pop("output_options", None)

    if output_options is None:
        output_options = [{} for i in range(nb_out)]
    elif nb_out > 0 and len(output_options) != nb_out:
        raise ValueError(
            "the length of 'input_options' must match the number of encoded inputs"
        )
    extra_outputs = kwargs.pop("extra_outputs", None)

    open_kws -= {"output_options", "extra_outputs"}
    for k in open_kws:
        if k in kwargs:
            raise TypeError(f"Invalid keyword inputs found: {k}")

    if "overwrite" in runner_kws and runner_kws["overwrite"] is not None:
        raise TypeError("'overwrite' keyword is not supported in the encoder mode.")

    return PipedFFmpegRunner.open_media_encoder(
        input_options, output_options, kwargs, extra_inputs, extra_outputs, **runner_kws
    )


def _open_transcoder(
    nb_in: int,
    nb_out: int,
    urls: Literal["-"],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner:

    if urls != "-":
        raise TypeError("urls_fgs argument for a decoder must be '-' for a transcoder.")

    if len(args):
        raise TypeError(
            "ffmpegio.open() takes only two positional arguments in a transcoder."
        )

    input_options = kwargs.pop("input_options", None) or []
    if len(input_options) == 0:
        input_options = [{} for i in range(nb_in)]
    elif nb_in > 0 and len(input_options) != nb_in:
        raise ValueError(
            f"input_options argument must have {nb_in} elements to match the specified transcoder mode."
        )

    output_streams = kwargs.pop("output_streams", None) or []
    if len(output_streams) == 0:
        output_streams = [{} for i in range(nb_out)]
    elif nb_out > 0 and len(output_streams) != nb_out:
        raise ValueError(
            f"output_streams argument must have {nb_out} elements to match the specified transcoder mode."
        )

    extra_inputs = kwargs.pop("extra_inputs", None)
    extra_outputs = kwargs.pop("extra_outputs", None)

    used_kws = {"input_options", "output_options", "extra_inputs", "extra_outputs"}
    open_kws = _open_kws_set() - used_kws
    for k in open_kws:
        if k in kwargs:
            raise TypeError(f"Invalid transcoder keyword inputs found: {k}")

    if "overwrite" in runner_kws and runner_kws["overwrite"] is not None:
        raise TypeError("'overwrite' keyword is not supported in the transcoder mode.")

    return PipedFFmpegRunner.open_media_transcoder(
        input_options, output_streams, kwargs, extra_inputs, extra_outputs, **runner_kws
    )
