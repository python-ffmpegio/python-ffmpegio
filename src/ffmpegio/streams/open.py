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

from .. import utils
from .._typing import (
    IO,
    DTypeString,
    FFmpegOptionDict,
    FFmpegUrlType,
    Literal,
    LiteralString,
    ProgressCallable,
    Sequence,
    ShapeTuple,
    Unpack,
    overload,
)
from ..configure import (
    FFmpegInputOptionTuple,
    FFmpegInputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegNoPipeInputOptionTuple,
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
    urls_fgs: FFmpegInputUrlNoPipe
    | IO
    | list[FFmpegInputUrlNoPipe | FFmpegNoPipeInputOptionTuple],
    mode: Literal["rv", "ra"],
    /,
    *,
    map: str | None = None,
    extra_outputs: list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None,
    squeeze: bool = False,
    blocksize: int | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> StdFFmpegRunner:
    """open a single-stream reader

    :param urls_fgs: URL string of the file or format/device object. It can be
                     an input filtergraph object or other input ffmpegio objects.
                     The input could also be fed by a readable file object.
                     Multiple input sources could be assigned to feed a complex
                     filtergraph.
    :param mode: ``'rv'`` to read video data or ``'ra'`` to read audio
    :param map: FFmpeg map output option, defaults to ``"0:V:0"`` for video and
                ``"0:a:0"`` for audio. The map option is required if ``options``
                contains the ``filter_complex`` option.
    :param extra_outputs: extra encoded output urls, Each element is a tuple
                          pair of url and output option dict. The url must be
                          a url and not pipes or pipe objects.
    :param squeeze: ``True`` (default) to eliminate raw output's singleton
                    dimensions. Use ``False`` to always return 2D array for
                    audio and 4D array for video.
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param overwrite: ``True`` to overwrite extra_outputs if they exist, defaults to ``False``
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
    :param options: global/default FFmpeg options. For output and global options,
                    use FFmpeg option names as is. For input options, append "_in" to the
                    option name. For example, r_in=2000 to force the input frame rate
                    to 2000 frames/s (see :doc:`options`).
    :return: reader stream object
    """


@overload
def open(
    urls: FFmpegOutputUrlNoPipe
    | list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple],
    mode: Literal["wv", "wa"],
    /,
    input_rate: int | Fraction,
    *,
    input_shape: ShapeTuple | None = None,
    input_dtype: DTypeString | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    overwrite: bool = False,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> StdFFmpegRunner:
    """open a single-stream media writer

    :param urls_fgs: URL of the output file or format/device object. The output
                     could also be written to a writable file object. Multiple
                     files (and optionally their options) are specified, they
                     are generated simultaneously.
    :param mode: ``'wv'`` to create a video file or ``'wa'`` to create an audio
                 file
    :param input_rate: input frame rate (video) or sampling rate (audio)
    :param input_shape: input video frame size (height, width) or number of input
                        audio channel, defaults to auto-detect
    :param input_dtype: input data format in a Numpy dtype string, defaults to
                        auto-detect
    :param extra_inputs: extra media source files/urls, defaults to None. A tuple
                         of an url and input option dict may be assigned.
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param overwrite: True to overwrite output URL, defaults to False.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    fg: str | FilterGraphObject | Literal["-"],
    mode: Literal["fv", "fa", "v->v", "a->a", "v->a", "a->v"],
    /,
    input_rate: int | Fraction,
    *,
    input_shape: ShapeTuple | None = None,
    input_dtype: DTypeString | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: (
        list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
    ) = None,
    squeeze: bool = False,
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> SISOFFmpegFilter:
    """open a single-input single-output media filter

    :param urls_fgs: URL of the file or format/device object to write media stream to. The output
                     could also be written to a bytes object or a writable file object.
    :param mode: `'wv'` or `'v->ev'` to create a video file, `'wa'` or `'a->e'` to create an audio file
    :param input_rate: Input frame rate (video) or sampling rate (audio)
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param extra_inputs: extra media source files/urls, defaults to None
    :param overwrite: True to overwrite output URL, defaults to False.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
    :param options: global/default FFmpeg options. For output and global options,
                    use FFmpeg option names as is. For input options, append "_in" to the
                    option name. For example, r_in=2000 to force the input frame rate
                    to 2000 frames/s (see :doc:`options`). These input and output options
                    specified here are treated as default, common options, and the
                    url-specific duplicate options in the ``inputs`` or ``outputs``
                    sequence will overwrite those specified here.
    :return: audio writer stream object

    """


@overload
def open(
    urls: FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict],
    mode: MultiReaderModeLiteral,
    /,
    *,
    output_options: Sequence[MapString | FFmpegOptionDict]
    | dict[str, MapString | FFmpegOptionDict]
    | None = None,
    extra_outputs: Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None,
    squeeze: bool = False,
    primary_output: int | None = None,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a multi-stream reader

    :param urls_fgs: URL of the file or format/device object to obtain a video stream from.
                     It can also be an input filtergraph object or string. The input
                     could also be fed by a buffered bytes-like data object or a readable file object.
    :param mode: ``'rv'`` to read video data or ``'ra'`` to read audio
    :param output_options: output stream options:
                - `None` to include all input streams OR all filtergraph outputs
                - a sequence of str to specify stream specifiers with file id's
                - a sequence of output option dict with `'map'` item to output-specific
                  options
                - a dict with map specifier or user keys to specify output options,
                  again to specify output-specific options. The keys will be used
                  as the keys of the raw data output, and can be different from
                  the `'map'` option so long as the `'map'` option is given in the
                  dict.
                - None to select all available streams
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    urls_fgs: FFmpegUrlType,
    mode: MultiWriterModeLiteral,
    /,
    input_rates: list[int | Fraction],
    *,
    input_shapes: list[ShapeTuple] | None = None,
    input_dtypes: list[DTypeString] | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a single-stream media writer

    :param urls_fgs: URL of the file or format/device object to write media stream to. The output
                     could also be written to a bytes object or a writable file object.
    :param mode: ``'wv'`` to create a video file or ``'wa'`` to create an audio file
    :param input_rate: Input frame rate (video) or sampling rate (audio)
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param extra_inputs: extra media source files/urls, defaults to None
    :param overwrite: True to overwrite output URL, defaults to False.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    urls_fgs: str | FilterGraphObject | list[str | FilterGraphObject],
    mode: MIMOFilterModeLiteral,
    /,
    input_rates: list[int | Fraction],
    *,
    input_shapes: list[ShapeTuple] | None = None,
    input_dtypes: list[DTypeString] | None = None,
    output_options: Sequence[MapString | FFmpegOptionDict]
    | dict[str, MapString | FFmpegOptionDict]
    | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    squeeze: bool = False,
    primary_output: int | None = None,
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """Open a multiple-input-multiple-output media filter

    :param fg: Filtergraph expression or object.
    :param mode: `'f'` with a combination of input media types (e.g., ``'rvva'``
                 if two video input streams and one audio input stream. The output
                 media types are automatically detected. Alternately, an arrow
                 convention specifying input and output media types, e.g.,
                 `'vva->v'` to output a video stream, which stacks the two input
                 video streams and the spectrum of the audio input stream.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    output_options: Sequence[MapString | FFmpegOptionDict]
    | dict[str, MapString | FFmpegOptionDict]
    | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    squeeze: bool = False,
    primary_output: int | None = None,
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a media decoder (encoded streams in, raw streams out)

    :param urls_fgs: ``'-'`` to indicate pipe-in pipe-out operation
    :param mode: `'wv'` or `'v->ev'` to create a video file, `'wa'` or `'a->e'` to create an audio file
    :param f: FFmpeg format option for the output stream
    :param input_rate: Input frame rate (video) or sampling rate (audio)
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param extra_inputs: _description_, defaults to None
    :param overwrite: True to overwrite output URL, defaults to False.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    output_options: list[FFmpegOptionDict],
    input_options: list[FFmpegOptionDict] | None = None,
    input_dtypes: list[DTypeString] | None = None,
    input_shapes: list[ShapeTuple] | None = None,
    extra_inputs: list[FFmpegInputOptionTuple] | None = None,
    extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
    blocksize: int | None = None,
    enc_blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    overwrite: bool | None = None,
    sp_kwargs: dict | None = None,
    **options: FFmpegOptionDict,
) -> PipedFFmpegRunner:
    """open a media encoder (raw streams in, encoded streams out)

    :param urls_fgs: ``'-'`` to indicate pipe-in pipe-out operation
    :param mode: `'wv'` or `'v->ev'` to create a video file, `'wa'` or `'a->e'` to create an audio file
    :param f: FFmpeg format option for the output stream
    :param input_rates: Input frame rate (video) or sampling rate (audio)
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param extra_inputs: _description_, defaults to None
    :param overwrite: True to overwrite output URL, defaults to False.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> PipedFFmpegRunner:
    """open a media transcoder (encoded streams in, encoded streams out)

    :param urls_fgs: ``'-'`` to indicate pipe-in pipe-out operation
    :param mode: `'wv'` or `'v->ev'` to create a video file, `'wa'` or `'a->e'` to create an audio file
    :param f: FFmpeg format option for the output stream
    :param extra_inputs: _description_, defaults to None
    :param overwrite: True to overwrite output URL, defaults to False.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                    `subprocess.Popen()` call used to run the FFmpeg, defaults
                    to None
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
    # 'output_options', 'extra_outputs', 'squeeze'

    op_mode, in_types, out_types = _parse_mode(mode)
    if urls_fgs == "-" and op_mode in "rw":
        raise ValueError(
            f"{'Input of a reader' if op_mode == 'r' else 'Output of a writer'} cannot be piped ('-'). Provide at least one URL."
        )

    runner_kws = {
        k: kwargs[k]
        for k in (
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
        runner = _open_decoder(len(in_types), out_types, kwargs, runner_kws)
    elif op_mode == "e":
        runner = _open_encoder(in_types, len(out_types), args, kwargs, runner_kws)
    else:
        runner = _open_transcoder(len(in_types), len(out_types), kwargs, runner_kws)

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
        elif op_mode in "ew":
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
            "output_options",
            "extra_outputs",
            "squeeze",
        ]
    )


def _open_reader(
    out_types: str,
    urls: FFmpegInputUrlComposite | Sequence[FFmpegInputUrlComposite],
    kwargs: dict,
    runner_kws: dict,
) -> StdFFmpegRunner | PipedFFmpegRunner:
    # # single reader
    # urls_fgs,
    # mode: Literal["rv", "ra"],
    # /,
    # *,
    # map: str | None = None,
    # extra_outputs: list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None,
    # squeeze: bool = False,
    # **options: Unpack[FFmpegOptionDict],

    # # multi reader
    # urls: FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict],
    # mode: MultiReaderModeLiteral,
    # /,
    # *,
    # output_options: Sequence[FFmpegOptionDict]
    # extra_outputs: Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None,
    # **options: Unpack[FFmpegOptionDict],

    nout = len(out_types)
    single_output = nout == 1  # single encoded stream

    urls = [urls] if utils.is_valid_input_url(urls) or isinstance(urls, tuple) else urls

    output_options = [{}] if single_output else kwargs.pop("output_options", None)
    extra_outputs = kwargs.pop("extra_outputs", None)
    squeeze = kwargs.pop("squeeze", None)

    used_kws = set("extra_outputs", "squeeze")
    if single_output:
        used_kws.add("output_options")
    open_kws = _open_kws_set() - used_kws
    if len(open_kws):
        raise TypeError("Invalid keyword inputs found")

    if len(out_types) == 0:  # autodetect (unless map is specified)
        single_output = single_output and "map" in kwargs
    else:
        if output_options is None:
            output_options = [{} for _ in range(nout)]
        elif nout != len(output_options):
            raise ValueError(
                "number of outputs in mode does not match the number of output options specified."
            )

        # use default map options
        if (
            "map" not in kwargs
            and len(urls) == 1
            and not utils.find_filter_complex_option(kwargs)
        ):
            stream_counts = {"a": 0, "v": 0}
            for mtype, opts in zip(out_types, output_options):
                st = stream_counts[mtype]
                stream_counts[mtype] += 1
                if "map" not in opts:
                    opts["map"] = f"0:{mtype}:{st}"

    return (
        StdFFmpegRunner.open_simple_reader(
            urls,
            output_options[0],
            kwargs,
            squeeze,
            extra_outputs,
            **runner_kws,
        )
        if single_output
        else PipedFFmpegRunner.open_media_reader(
            urls, output_options, kwargs, squeeze, extra_outputs, **runner_kws
        )
    )


def _open_writer(
    in_types: str,
    urls: FFmpegInputUrlComposite | Sequence[FFmpegInputUrlComposite],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner | StdFFmpegRunner:
    # # single writer
    # urls: FFmpegOutputUrlNoPipe
    # | list[FFmpegOutputUrlNoPipe | FFmpegNoPipeOutputOptionTuple],
    # mode: Literal["wv", "wa"],
    # /,
    # input_rate: int | Fraction,
    # *,
    # extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # options: Unpack[FFmpegOptionDict],

    # # multi-writer
    # urls_fgs: FFmpegUrlType,
    # mode: MultiWriterModeLiteral,
    # /,
    # input_rates: list[int | Fraction],
    # *,
    # output_options: Sequence[MapString | FFmpegOptionDict]
    # | dict[str, MapString | FFmpegOptionDict]
    # | None = None,
    # extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # options: Unpack[FFmpegOptionDict],

    nargs = len(args)
    if nargs > 1:
        raise TypeError(
            f"ffmpegio.open() takes two to three positional arguments ({2 + len(args)} given) to open a writer"
        )

    single_input = len(in_types) == 1  #

    used_kws = ["output_options", "extra_inputs"]
    output_options = kwargs.pop("output_options", None)
    # extra_inputs

    # if single_input:
    # input_rate
    # input_rates


def _open_filter(
    in_types: str,
    out_types: str,
    fgs: str | FilterGraphObject | Sequence[str | FilterGraphObject] | None,
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> SISOFFmpegFilter:
    # siso filter
    # fg: str | FilterGraphObject | Literal['-'],
    # mode: Literal["fv", "fa", "v->v", "a->a", "v->a", "a->v"],
    # /,
    # input_rate: int | Fraction,
    # *,
    # input_shape: ShapeTuple | None = None,
    # input_dtype: DTypeString | None = None,
    # extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # extra_outputs: (
    #     list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
    # ) = None,
    # squeeze: bool = False,
    # overwrite: bool = False,
    # show_log: bool | None = None,
    # progress: ProgressCallable | None = None,
    # blocksize: int | None = None,
    # timeout: float | None = None,
    # sp_kwargs: dict | None = None,
    # **options: Unpack[FFmpegOptionDict],

    # mimo filter
    # urls_fgs: str | FilterGraphObject | list[str | FilterGraphObject],
    # mode: MIMOFilterModeLiteral,
    # /,
    # input_rates: list[int | Fraction],
    # *,
    # input_shapes: list[ShapeTuple] | None = None,
    # input_dtypes: list[DTypeString] | None = None,
    # extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # overwrite: bool = False,
    # show_log: bool | None = None,
    # progress: ProgressCallable | None = None,
    # blocksize: int | None = None,
    # timeout: float | None = None,
    # sp_kwargs: dict | None = None,
    # **options: Unpack[FFmpegOptionDict],

    if len(args) > 1:
        raise TypeError(
            f"ffmpegio.open() takes two arguments ({2 + len(args)} given) to open a writer"
        )

    single_input = len(in_types) > 1
    single_output = len(out_types) > 1
    matched_io = in_types == out_types

    is_siso = single_output and single_input and matched_io

    if is_siso:
        StreamClass = SISOFFmpegFilter
        filter = StreamClass(fgs, *args, **kwargs)
    else:
        StreamClass = PipedFFmpegRunner
        rates = args[0] if len(args) else kwargs.pop("input_rates_or_opts")
        filter = StreamClass(fgs, in_types, *rates, **kwargs)

    return filter


def _open_decoder(
    nb_in: int,
    out_types: str,
    urls: Literal["-"],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner:
    # decoder
    # urls_fgs: Literal["-"],
    # mode: DecoderModeLiteral,  # r"e+-\>[av]+",
    # /,
    # *,
    # output_options: list[MapString, FFmpegOptionDict] | None = None,
    # extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # squeeze: bool = False,
    # overwrite: bool = False,
    # show_log: bool | None = None,
    # progress: ProgressCallable | None = None,
    # blocksize: int | None = None,
    # queuesize: int | None = None,
    # timeout: float | None = None,
    # sp_kwargs: dict | None = None,
    # **options: Unpack[FFmpegOptionDict],

    if urls is not None:
        raise TypeError("urls_fgs argument for a filter must be None.")

    nargs = len(args)
    if nargs not in (0, 2) or (nargs == 3 and "output_options" in kwargs):
        raise TypeError(
            f"ffmpegio.open() takes two or four arguments ({2 + len(args)} given) to open a filter."
        )

    return PipedFFmpegRunner.open_media_decoder(*args, **kwargs)


def _open_encoder(
    in_types: str,
    nb_out: int,
    urls: Litera["-"],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner:
    # input_rates: list[int|Fraction]|None = None,
    # input_options: list[FFmpegOptionDict]|None=None,
    # output_options: list[FFmpegOptionDict]|None=None,
    # input_dtypes: list[DTypeString] | None = None,
    # input_shapes: list[ShapeTuple] | None = None,
    # extra_inputs: list[FFmpegInputOptionTuple] | None = None,
    # extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
    # primary_output: int | None = None,
    # blocksize: int | None = None,
    # enc_blocksize: int | None = None,
    # queuesize: int | None = None,
    # timeout: float | None = None,
    # progress: ProgressCallable | None = None,
    # show_log: bool | None = None,
    # overwrite: bool | None = None,
    # sp_kwargs: dict | None = None,
    # **options: FFmpegOptionDict,
    nargs = len(args)
    if nargs == 1:
        input_rates = args[0]
    else:
        input_rates = kwargs.pop("input_rates", None)
        if nargs != 0:
            raise TypeError(
                "ffmpegio.open() takes only three positional arguments for encoder mode."
            )
    # check kwargs for unsupported keyword arguments

    input_options = kwargs.pop("input_options", None) or []

    output_options = kwargs.pop("output_options", None) or []
    if len(output_options) == 0:
        output_options = [{} for i in range(nb_out)]
    elif len(output_options) != nb_out:
        raise ValueError(
            f"output_options argument must have {nb_out} elements to match the specified transcoder mode."
        )

    # input_stream_types: list[Literal["a", "v"]],
    # input_stream_opts: list[FFmpegOptionDict],
    return PipedFFmpegRunner.open_media_encoder(*args, **kwargs)


def _open_transcoder(
    nb_in: int,
    nb_out: int,
    urls: Literal["-"],
    args: tuple,
    kwargs: dict,
    runner_kws: dict,
) -> PipedFFmpegRunner:
    # input_options: list[FFmpegOptionDict] | None = None,
    # output_options: list[FFmpegOptionDict] | None = None,
    # extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    # overwrite: bool = False,
    # show_log: bool | None = None,
    # progress: ProgressCallable | None = None,
    # blocksize: int | None = None,
    # queuesize: int | None = None,
    # timeout: float | None = None,
    # sp_kwargs: dict | None = None,
    # **options: Unpack[FFmpegOptionDict],

    if len(args):
        raise TypeError("ffmpegio.open() takes only two positional arguments.")

    input_options = kwargs.pop("input_options", None) or []
    if len(input_options) == 0:
        input_options = [{} for i in range(nb_in)]
    elif len(input_options) != nb_in:
        raise ValueError(
            f"input_options argument must have {nb_in} elements to match the specified transcoder mode."
        )

    output_options = kwargs.pop("output_options", None) or []
    if len(output_options) == 0:
        output_options = [{} for i in range(nb_out)]
    elif len(output_options) != nb_out:
        raise ValueError(
            f"output_options argument must have {nb_out} elements to match the specified transcoder mode."
        )

    return PipedFFmpegRunner.open_media_transcoder(
        input_options, output_options, **kwargs
    )
