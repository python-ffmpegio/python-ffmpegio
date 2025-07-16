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

from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import overload, Literal, Sequence, Unpack, LiteralString
from ._typing import DTypeString, ShapeTuple
from fractions import Fraction
import re

from ._typing import ProgressCallable, Literal, FFmpegOptionDict, FFmpegUrlType
from .configure import (
    IO,
    Buffer,
    FFmpegInputUrlComposite,
    FFmpegOutputUrlComposite,
    FFConcat,
)
from .filtergraph.abc import FilterGraphObject

from . import streams, utils


@overload
def open(
    urls_fgs: FFmpegUrlType | FilterGraphObject | FFConcat | Buffer | IO,
    mode: Literal["rv", "ra", "e->v", "e->a"],
    *,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.SimpleAudioReader | streams.SimpleVideoReader:
    """open a single-source reader (`mode = "rv" | "ra" | "e->v" | "e->a"`)

    :param urls_fgs: URL of the file or format/device object to obtain a media stream from.
                     It can also be an input filtergraph object or string. The input
                     could also be fed by a buffered bytes-like data object or a readable file object.
    :param mode: `'rv'` or `'e->v'` to read video data, `'ra'` or `'e->a'` to read audio data
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    urls_fgs: FFmpegUrlType | IO | Buffer,
    mode: Literal["wv", "wa", "v->e", "a->e"],
    input_rate: int | Fraction,
    *,
    input_shape: ShapeTuple = None,
    input_dtype: DTypeString = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.SimpleAudioWriter | streams.SimpleVideoReader:
    """open a single-destination writer (`mode = "wv" | "wa" | "v->e" | "a->e"`)

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
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    urls_fgs: None | Literal["pipe", "-", "pipe:0"],
    mode: Literal["e->v", "e->a"],
    *,
    f_in: str,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.StdAudioDecoder | streams.StdVideoDecoder:
    """open a piped single-source reader (`mode = "rv" | "ra" | "e->v" | "e->a"`)

    :param urls_fgs: A pipe path or `None` to indicate input is provided by `write_encoded()`.
    :param mode: `'rv'` or `'e->v'` to read video data, `'ra'` or `'e->a'` to read audio data
    :param f_in: FFmpeg format option for the input stream
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto-set)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    urls_fgs: Literal["-", "pipe", "pipe:1"] | None,
    mode: Literal["wv", "wa", "v->e", "a->e"],
    input_rate: int | Fraction,
    *,
    f: str,
    input_shape: ShapeTuple = None,
    input_dtype: DTypeString = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    overwrite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.StdAudioEncoder | streams.StdVideoEncoder:
    """open a piped single-destination writer (`mode = "wv" | "wa" | "v->e" | "a->e"`)

    :param urls_fgs: A pipe path or `None` to indicate input is provided by `write_encoded()`.
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
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    urls_fgs: str | FilterGraphObject,
    mode: Literal["fv", "fa", "v->v", "a->a"],
    input_rate: int | Fraction,
    *,
    input_shape: ShapeTuple = None,
    input_dtype: DTypeString = None,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.StdAudioFilter | streams.StdVideoFilter:
    """open a single-input, single-output (SISO) filter

    :param urls_fgs: a filtergraph expression
    :param mode: `"fv"` or `"v->v"` to specify video filter, and `"fa"` or `"a->a"` to specify audio filter
    :param input_rate: input frame rate (video) or sampling rate (audio)
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (auto)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    :return: filter stream object
    """


@overload
def open(
    urls_fgs: Literal[None],
    mode: LiteralString,
    *,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.StdMediaTranscoder:
    """open a single-input, single-output streamed transcoder

    :param urls_fgs: set to `None` as the primary I/O is conducted via `write()`
                     and `read()` operations.
    :param mode: transcoding mode is activated by setting `mode = 't'`
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param extra_outputs: list of additional output destinations, defaults to None. Each destination
                            may be url string or a pair of a url string and an option dict.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (64 kB)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    :return: transcoder stream object
    """


@overload
def open(
    urls_fgs: Sequence[
        FFmpegInputUrlComposite | tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
    ],
    mode: LiteralString,
    *,
    map: Sequence[str] | dict[str, FFmpegOptionDict] | None = None,
    ref_stream: int = 0,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.PipedMediaReader:
    """open a multi-stream reader

    :param urls_fgs: a list of input sources
    :param mode: `'r'` + an optional sequence of `'v'`s and `'a'`s for each output streams. Alternately,
                 `eee->vva` format could be used with the left hand side repeating the `'e'`s to indicate
                 the number of inputs.)
    :param map: a list of FFmpeg stream specifiers to specify the streams to retrieve, defaults to `None`
                to retrieve all streams if `mode='r'` or as many streams as `mode` specifies in the order
                of appearances.
    :param ref_stream: index of the output stream, which is used as a reference stream to pace the read
                       operations, defaults to 0
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (64 kB)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    :return: _description_
    """


@overload
def open(
    urls_fgs: (
        FFmpegOutputUrlComposite
        | list[
            FFmpegOutputUrlComposite | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
        ]
    ),
    mode: LiteralString,
    rates_or_opts_in: Sequence[int | Fraction | FFmpegOptionDict],
    *,
    input_dtypes: list[DTypeString] | None = None,
    input_shapes: list[ShapeTuple] | None = None,
    merge_audio_streams: bool | Sequence[int] = False,
    merge_audio_ar: int | None = None,
    merge_audio_sample_fmt: str | None = None,
    merge_audio_outpad: str | None = None,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    overwite: bool = False,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.PipedMediaWriter:
    """open a multi-stream writer

    :param urls_fgs: a list of output encoded streams. Specific FFmpeg output options could be specified for
                     an output by providing a pair of the url and its option `dict`.
    :param mode: `'w'` followed by a sequence of input stream types, e.g., `'vav'` if video, audio, and video
                 raw data streams will be written (in that order). Alternately, `vav->ee` format could be used.
                 (The right hand side has `'e'` repeated for as many outputs as written.)
    :param rates_or_opts_in: _description_
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param merge_audio_streams: _description_, defaults to False
    :param merge_audio_ar: _description_, defaults to None
    :param merge_audio_sample_fmt: _description_, defaults to None
    :param merge_audio_outpad: _description_, defaults to None
    :param extra_inputs: extra media source files/urls, defaults to None
    :param overwrite: True to overwrite destination file. Ignored if any of the
                      output is streamed.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (64 kB)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    :return: _description_
    """


@overload
def open(
    urls_fgs: str | FilterGraphObject | Sequence[str | FilterGraphObject],
    mode: LiteralString,
    input_rates_or_opts: Sequence[int | Fraction | FFmpegOptionDict],
    *,
    input_dtypes: list[DTypeString] | None = None,
    input_shapes: list[ShapeTuple] | None = None,
    ref_output: int = 0,
    output_options: dict[str, FFmpegOptionDict] | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.PipedMediaFilter:
    """open a multi-stream filter

    :param urls_fgs: _description_
    :param mode: _description_
    :param input_rates_or_opts: _description_
    :param input_shape: input video frame size (height, width) or number of input audio channel, defaults
                     to None (auto-detect)
    :param input_dtype: input data format in a Numpy dtype string, defaults to None (auto-detect)
    :param extra_inputs: extra media source files/urls, defaults to None
    :param ref_output: index of the output stream, which is used as a reference stream to pace the read
                       operations, defaults to 0
    :param output_options: _description_, defaults to None
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (64 kB)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    :return: transcoder stream object
    """


@overload
def open(
    urls_fgs: Literal[None],
    mode: LiteralString,
    input_options: Sequence[FFmpegOptionDict],
    output_options: Sequence[FFmpegOptionDict],
    *,
    extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
    show_log: bool | None = None,
    progress: ProgressCallable | None = None,
    blocksize: int | None = None,
    queuesize: int | None = None,
    default_timeout: float | None = None,
    sp_kwargs: dict = None,
    **options: Unpack[FFmpegOptionDict],
) -> streams.PipedMediaTranscoder:
    """open a streamed transcoder

    :param urls_fgs: set to `None` as the primary I/O is conducted via `write()`
                     and `read()` operations.
    :param mode: transcoding mode is activated by setting `mode = 't'` or '`ee->e'` The `'->'`
                 operator optionally specifies the number of input and output files.
    :param input_options: FFmpeg input option dicts of all the input pipes. Each dict
                            must contain the `"f"` option to specify the media format.
    :param output_options: FFmpeg output option dicts of all the output pipes. Each dict
                            must contain the `"f"` option to specify the media format.
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param extra_outputs: list of additional output destinations, defaults to None. Each destination
                            may be url string or a pair of a url string and an option dict.
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param progress: progress callback function, defaults to None
    :param blocksize: Background reader queue's item size in bytes, defaults to `None` (64 kB)
    :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
    :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
    :return: transcoder stream object
    """


def open(
    urls_fgs: (
        FFmpegInputUrlComposite
        | FFmpegOutputUrlComposite
        | Sequence[FFmpegInputUrlComposite | FFmpegOutputUrlComposite]
        | None
    ),
    mode: LiteralString,
    *args,
    **kwargs,
):
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

    try:
        op_mode, in_types, out_types = _parse_mode(mode)
        if op_mode == "r":
            runner = _create_reader(out_types, urls_fgs, args, kwargs)
        elif op_mode == "w":
            runner = _create_writer(in_types, urls_fgs, args, kwargs)
        elif op_mode == "f":
            runner = _create_filter(in_types, out_types, urls_fgs, args, kwargs)
        else:
            runner = _create_transcoder(urls_fgs, args, kwargs)

        # TODO - check io types, display warning if mismatched

    except:
        raise

    return runner


def _parse_mode(mode: str) -> tuple[str, str, str]:

    it = re.finditer(r"([rwft])|(-\>)", mode)
    try:
        m = next(it)
    except StopIteration as e:
        raise ValueError(
            f'{mode=} is missing the operation specifier ("r", "w", "f", "t", or "->")'
        ) from e
    try:
        next(it)
        raise ValueError(
            f'{mode=} specifies multiple the operation specifiers ("r", "w", "f", "t", or "->")'
        )
    except StopIteration as e:
        pass

    inputs = mode[: m.start()]
    outputs = mode[m.end() :]

    op_mode = m[1]
    if op_mode:
        if op_mode == "r":
            inputs = ""
            outputs = inputs + outputs
        else:
            inputs = inputs + outputs
            outputs = ""
        in_encoded = out_encoded = None
    else:
        in_encoded = all(c == "e" for c in inputs)
        out_encoded = all(c == "e" for c in outputs)
        op_mode = (
            ("t" if out_encoded else "r")
            if in_encoded
            else ("w" if out_encoded else "f")
        )

    if op_mode in "rt":  # encoded in
        if not in_encoded and any(c != "e" for c in inputs):
            raise ValueError(
                f"{mode=} specifies a raw input, which is not valid for the specified operation."
            )
    else:  # raw in
        if not all(c in "av" for c in inputs):
            raise ValueError(
                f"{mode=} specifies an encoded input, which is not valid for the specified operation."
            )

    if op_mode in "wt":  # encoded out
        if not out_encoded and any(c != "e" for c in outputs):
            raise ValueError(
                f"{mode=} specifies a raw output, which is not valid for the specified operation."
            )
    else:  # raw out
        if not all(c in "av" for c in outputs):
            raise ValueError(
                f"{mode=} specifies an encoded output, which is not valid for the specified operation."
            )

    return op_mode, inputs, outputs


def _create_reader(
    out_types: str,
    urls: FFmpegInputUrlComposite | Sequence[FFmpegInputUrlComposite],
    args: tuple,
    kwargs: dict,
) -> (
    streams.PipedMediaReader
    | streams.StdAudioDecoder
    | streams.StdVideoDecoder
    | streams.SimpleAudioReader
    | streams.SimpleVideoReader
):

    if len(args):
        raise TypeError(
            f"ffmpegio.open() takes two arguments ({2+len(args)} given) to open a reader"
        )

    single_url = utils.is_valid_input_url(urls)  # else a sequence of urls
    if single_url:
        urls = [urls]
    elif len(urls) == 1 and utils.is_valid_input_url(urls[0]):
        single_url = True

    map_option = utils.as_multi_option(kwargs.get("map", None))
    if map_option is None:
        map_option = out_types

    is_audio = out_types == "a"
    is_siso = single_url and len(map_option) == 1

    if is_siso and utils.is_pipe(urls[0]):
        StreamClass = streams.StdAudioDecoder if is_audio else streams.StdVideoDecoder
        reader = StreamClass(**kwargs)
    else:
        StreamClass = (
            streams.PipedMediaReader
            if not is_siso
            else streams.SimpleAudioReader if is_audio else streams.SimpleVideoReader
        )
        reader = StreamClass(*urls, **kwargs)

    return reader


def _create_writer(
    in_types: str,
    urls: FFmpegInputUrlComposite | Sequence[FFmpegInputUrlComposite],
    args: tuple,
    kwargs: dict,
) -> (
    streams.PipedMediaWriter
    | streams.StdAudioEncoder
    | streams.StdVideoEncoder
    | streams.SimpleAudioWriter
    | streams.SimpleVideoWriter
):

    if len(args) > 1:
        raise TypeError(
            f"ffmpegio.open() takes two arguments ({2+len(args)} given) to open a writer"
        )

    single_output = utils.is_valid_output_url(urls)  # else a sequence of urls
    if single_output:
        urls = [urls]
    elif len(urls) == 1 and utils.is_valid_output_url(urls[0]):
        single_output = True

    single_input = len(in_types) > 1

    is_siso = single_output and single_input
    is_audio = in_types == "a"

    if not is_siso:
        rates = args[0] if len(args) else kwargs.pop("input_rates_or_opts")
        writer = streams.PipedMediaWriter(urls, in_types, *rates, **kwargs)
    elif utils.is_pipe(urls[0]):
        StreamClass = streams.StdAudioEncoder if is_audio else streams.StdVideoEncoder
        writer = StreamClass(*args, **kwargs)
    else:
        StreamClass = (
            streams.SimpleAudioWriter if is_audio else streams.SimpleVideoWriter
        )
        writer = StreamClass(*urls, *args, **kwargs)
    return writer


def _create_filter(
    in_types: str,
    out_types: str,
    fgs: str | FilterGraphObject | Sequence[str | FilterGraphObject],
    args: tuple,
    kwargs: dict,
) -> streams.PipedMediaFilter | streams.StdAudioFilter | streams.StdVideoFilter:

    if len(args) > 1:
        raise TypeError(
            f"ffmpegio.open() takes two arguments ({2+len(args)} given) to open a writer"
        )

    single_input = len(in_types) > 1
    single_output = len(out_types) > 1
    matched_io = in_types == out_types

    is_siso = single_output and single_input and matched_io
    is_audio = in_types == "a"

    if is_siso:
        StreamClass = streams.StdAudioFilter if is_audio else streams.StdVideoFilter
        filter = StreamClass(fgs, *args, **kwargs)
    else:
        rates = args[0] if len(args) else kwargs.pop("input_rates_or_opts")
        filter = streams.PipedMediaFilter(fgs, in_types, *rates, **kwargs)

    return filter


def _create_transcoder(
    urls: None, args: tuple, kwargs: dict
) -> streams.PipedMediaTranscoder | streams.StdMediaTranscoder:

    if urls is not None:
        raise TypeError("urls_fgs argument for a filter must be None.")

    nargs = len(args)
    if nargs not in (0, 2) or (nargs == 3 and "output_options" in kwargs):
        raise TypeError(
            f"ffmpegio.open() takes two or four arguments ({2+len(args)} given) to open a filter."
        )

    use_piped = args[0] if nargs else kwargs.get("input_options", None)

    return (
        streams.PipedMediaTranscoder(*args, **kwargs)
        if use_piped
        else streams.StdMediaTranscoder(*args, **kwargs)
    )
