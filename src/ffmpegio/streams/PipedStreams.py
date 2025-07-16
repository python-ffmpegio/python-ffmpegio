from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import Unpack
from collections.abc import Sequence
from .._typing import (
    DTypeString,
    ShapeTuple,
    ProgressCallable,
    RawDataBlob,
    Literal,
    InputSourceDict,
    OutputDestinationDict,
    FFmpegOptionDict,
)
from ..configure import (
    FFmpegArgs,
    FFmpegInputUrlComposite,
    FFmpegUrlType,
    MediaType,
    FFmpegOutputUrlComposite,
    InitMediaOutputsCallable,
)
from ..filtergraph.abc import FilterGraphObject
from contextlib import ExitStack

import sys
from time import time
from fractions import Fraction

from .. import configure, ffmpegprocess, plugins, utils, probe
from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError

from .BaseFFmpegRunner import (
    BaseFFmpegRunner,
    BaseRawInputsMixin,
    BaseRawOutputsMixin,
    BaseEncodedInputsMixin,
    BaseEncodedOutputsMixin,
)

# fmt:off
__all__ = ["PipedMediaReader", "PipedMediaWriter", "PipedMediaFilter", "PipedMediaTranscoder"]
# fmt:on


class _PipedFFmpegRunner(BaseFFmpegRunner):
    """Base class to run FFmpeg and manage its multiple I/O's"""

    def __init__(
        self,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict] | None,
        input_ready: Literal[True] | list[bool] | None,
        init_deferred_outputs: InitMediaOutputsCallable | None,
        deferred_output_args: list[FFmpegOptionDict | None],
        *,
        default_timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        queuesize: int | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Encoded media stream transcoder

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg output option dicts of all the output pipes. Each dict
                               must contain the `"f"` option to specify the media format.
        :param output_info: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param input_ready: indicates if input is ready (True) or need its first batch of data to
                            provide necessary information for the outputs
        :param init_deferred_outputs: function to initialize the outputs which have been deferred to
                                      configure until the first batch of input data is in
        :param deferred_output_args:
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
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
        """

        super().__init__(
            ffmpeg_args,
            input_info,
            output_info,
            input_ready,
            init_deferred_outputs,
            deferred_output_args,
            default_timeout,
            progress,
            show_log,
            sp_kwargs,
        )

        # set the default read block size for the referenc stream
        self._pipe_kws = {"queue_size": queuesize}

    def _assign_pipes(self):
        """pre-popen pipe assignment and initialization

        All named pipes must be 
        """
        if len(self._input_info):
            configure.assign_input_pipes(
                self._args["ffmpeg_args"],
                self._input_info,
                self._args["sp_kwargs"],
            )

        if len(self._output_info):
            configure.assign_output_pipes(
                self._args["ffmpeg_args"],
                self._output_info,
                self._args["sp_kwargs"],
            )

        configure.init_named_pipes(
            self._input_info, self._output_info, **self._pipe_kws, stack=self._stack
        )


class _RawInputMixin(BaseRawInputsMixin):

    _media_bytes = {"video": "video_bytes", "audio": "audio_bytes"}
    _array_to_opts = {
        "video": utils.array_to_video_options,
        "audio": utils.array_to_audio_options,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        hook = plugins.get_hook()
        self._get_bytes = {"video": hook.video_bytes, "audio": hook.audio_bytes}

        # input data must be initially buffered
        self._deferred_data = [[] for _ in range(len(self._input_info))]

    def _write_stream(
        self,
        info: OutputDestinationDict,
        stream_id: int,
        data: RawDataBlob,
        timeout: float | None,
    ):
        """write a raw media data to a specified stream (backend)"""

        media_type = info["media_type"]
        self._write_stream_bytes(self._get_bytes[media_type], stream_id, data, timeout)

    def write_stream(
        self, stream_id: int, data: RawDataBlob, timeout: float | None = None
    ):
        """write a raw media data to a specified stream

        :param stream_id: input stream index or label
        :param data: media data blob (depends on the active data conversion plugin)
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is written
                        to the buffer queue
        :return: currently available encoded data (bytes) if returning the encoded
                 data back to Python

        Write the given NDArray object, data, and return the number
        of bytes written (always equal to the number of data frames/samples,
        since if the write fails an OSError will be raised).

        When in non-blocking mode, a BlockingIOError is raised if the data
        needed to be written to the raw stream but it couldn’t accept all
        the data without blocking.

        The caller may release or mutate data after this method returns,
        so the implementation should only access data during the method call.

        """

        # get input stream information
        try:
            info = self._input_info[stream_id]
        except IndexError:
            raise FFmpegioError(f"{stream_id=} is an invalid input stream index.")

        if timeout is None:
            timeout = self.default_timeout

        self._write_stream(info, stream_id, data, timeout)

    def write(
        self,
        data: Sequence[RawDataBlob] | dict[int, RawDataBlob],
        timeout: float | None = None,
    ) -> bytes | None:
        """write data to all input streams

        :param data: media data blob keyed by stream index
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is written
                        to the buffer queue

        """

        it_data = data.items() if isinstance(data, dict) else enumerate(data)

        if timeout is None:
            timeout = self.default_timeout

        if timeout is not None:
            timeout += time()

        info = self._input_info
        for stream_id, stream_data in it_data:
            self._write_stream(
                info[stream_id],
                stream_id,
                stream_data,
                None if timeout is None else timeout - time(),
            )


class _EncodedInputMixin(BaseEncodedInputsMixin):

    def write_encoded_stream(
        self, stream_id: int, data: bytes, timeout: float | None = None
    ):
        """write a raw media data to a specified stream

        :param stream_id: input stream index or label
        :param data: media data bytes
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is written
                        to the buffer queue
        :return: currently available encoded data (bytes) if returning the encoded
                 data back to Python

        Write the given NDArray object, data, and return the number
        of bytes written (always equal to the number of data frames/samples,
        since if the write fails an OSError will be raised).

        When in non-blocking mode, a BlockingIOError is raised if the data
        needed to be written to the raw stream but it couldn’t accept all
        the data without blocking.

        The caller may release or mutate data after this method returns,
        so the implementation should only access data during the method call.

        """

        # get input stream information
        try:
            info = self._input_info[stream_id]
        except IndexError:
            raise FFmpegioError(f"{stream_id=} is an invalid input stream index.")

        if timeout is None:
            timeout = self.default_timeout

        self._write_encoded_stream(stream_id, info, data, timeout)

    def write_encoded(
        self,
        data: Sequence[RawDataBlob] | dict[int, RawDataBlob],
        timeout: float | None = None,
    ) -> bytes | None:
        """write data to all input streams

        :param data: media byte data keyed by stream index
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is written
                        to the buffer queue

        """

        it_data = data.items() if isinstance(data, dict) else enumerate(data)

        if timeout is None:
            timeout = self.default_timeout

        if timeout is not None:
            timeout += time()

        info = self._input_info
        for stream_id, stream_data in it_data:
            self._write_encoded_stream(
                stream_id,
                info[stream_id],
                stream_data,
                None if timeout is None else timeout - time(),
            )


class _RawOutputMixin(BaseRawOutputsMixin):
    def __init__(self, blocksize, ref_output, **kwargs):
        super().__init__(blocksize=blocksize, ref_output=ref_output, **kwargs)
        hook = plugins.get_hook()
        self._converters = {"video": hook.bytes_to_video, "audio": hook.bytes_to_audio}
        self._get_num = {"video": hook.video_frames, "audio": hook.audio_samples}

    def _read_stream(
        self,
        info: OutputDestinationDict,
        stream_id: int | str,
        n: int,
        timeout: float | None = None,
        squeeze: bool = False,
    ) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        converter = self._converters[info["media_type"]]
        dtype, shape, _ = info["raw_info"]
        counter = self._get_num[info["media_type"]]

        return self._read_stream_bytes(
            converter, counter, dtype, shape, info, stream_id, n, timeout, squeeze
        )

    def read_stream(
        self, stream_id: int | str, n: int, timeout: float | None = None
    ) -> RawDataBlob:
        """read selected output stream

        :param stream_id: stream index or label
        :param n: number of frames/samples to read, defaults to -1 to read as many as available
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is read
                        from the buffer queue
        :return: retrieved data

        Effect of mixing `n` and `timeout`
        ----------------------------------

        ===  =========  =========================================================================
        `n`  `timeout`  Behavior
        ===  =========  =========================================================================
        0    ---        Immediately returns
        >0   `None`     Wait indefinitely until `n` frames/samples are retrieved
        >0   `float`    Retrieve as many frames/samples up to `n` before `timeout` seconds passes
        <0   `None`     Wait indefinitely until FFmpeg terminates
        <0   `float`    Retrieve as many frames/samples until `timeout` seconds passes
        ===  =========  =========================================================================

        """

        if timeout is None:
            timeout = self.default_timeout

        info = self._output_info
        stream_id = utils.get_output_stream_id(info, stream_id)
        return self._read_stream(info[stream_id], stream_id, n, timeout)

    def read(self, n: int, timeout: float | None = None) -> dict[str, RawDataBlob]:
        """Read data from all output streams

        :param n: number of frames/samples of the reference output stream to read
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is read
                        from the buffer queue
        :return: retrieved data keyed by output streams

        Read all output streams and return retrieved data up to `n` frames/samples
        of the reference output stream. The amount of the data of the other output
        streams are calculated to match the time span of the retrieved reference
        data.

        The returned `dict` is keyed by the output labels.

        Effect of mixing `n` and `timeout`
        ----------------------------------

        ===  =========  =========================================================================
        `n`  `timeout`  Behavior
        ===  =========  =========================================================================
        0    ---        Immediately returns
        >0   `None`     Wait indefinitely until `n` frames/samples are retrieved
        >0   `float`    Retrieve as many frames/samples up to `n` before `timeout` seconds passes
        <0   `None`     Wait indefinitely until FFmpeg terminates
        <0   `float`    Retrieve as many frames/samples until `timeout` seconds passes
        ===  =========  =========================================================================
        """

        data = {}  # output

        if timeout is None:
            timeout = self.default_timeout

        if timeout is not None:
            timeout += time()

        get_timeout = lambda: None if timeout is None else max(timeout - time(), 0)

        get_all = n < 0 and timeout is None

        # read the reference stream
        i0 = self._ref
        n0 = self._n0[i0]
        ref_data = self._read_stream(self._output_info[i0], i0, n, get_timeout())
        if not get_all:
            # get the timestamp of the final frame
            T = (self._n0[i0] - n0) / self._rates[i0]

        # retrieve all the other streams up to T seconds mark
        for i, info in enumerate(self._output_info):
            if i != i0:
                if not get_all:
                    n1 = int(T * self._rates[i])
                    n = max(n1 - self._n0[i], 0)
                stream_data = self._read_stream(info, i, n, get_timeout())
            else:
                stream_data = ref_data
            data[info["user_map"]] = stream_data

        return data


class _EncodedOutputMixin(BaseEncodedOutputsMixin):

    def read_encoded_stream(
        self, stream_id: int, n: int, timeout: float | None = None
    ) -> bytes:
        """read selected output stream

        :param stream_id: stream index or label
        :param n: number of bytes to read
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is read
                        from the buffer queue
        :return: retrieved data

        Effect of mixing `n` and `timeout`
        ----------------------------------

        ===  =========  =========================================================================
        `n`  `timeout`  Behavior
        ===  =========  =========================================================================
        0    ---        Immediately returns
        >0   `None`     Wait indefinitely until `n` bytes are retrieved
        >0   `float`    Retrieve as many bytes up to `n` before `timeout` seconds passes
        <0   `None`     Wait indefinitely until FFmpeg terminates
        <0   `float`    Retrieve as many bytes until `timeout` seconds passes
        ===  =========  =========================================================================

        """

        if timeout is None:
            timeout = self.default_timeout

        info = self._output_info
        stream_id = utils.get_output_stream_id(info, stream_id)
        return self._read_encoded_stream(info[stream_id], n, timeout)

    def readall_encoded(self, timeout: float | None = None) -> dict[str, bytes]:
        """Read available data from all output streams

        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until FFmpeg stops
        :return: retrieved data keyed by output streams

        """

        data = {}  # output

        if timeout is None:
            timeout = self.default_timeout

        if timeout is not None:
            timeout += time()

        get_timeout = lambda: None if timeout is None else max(timeout - time(), 0)

        # retrieve all the other streams up to T seconds mark
        for i, info in enumerate(self._output_info):
            data[i] = self._read_encoded_stream(info, -1, get_timeout())

        return data


class PipedMediaReader(_EncodedInputMixin, _RawOutputMixin, _PipedFFmpegRunner):

    def __init__(
        self,
        *urls: *tuple[FFmpegInputUrlComposite | tuple[FFmpegUrlType, FFmpegOptionDict]],
        map: Sequence[str] | dict[str, FFmpegOptionDict] | None = None,
        ref_stream: int = 0,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Read video and audio data from multiple media files

        :param *urls: URLs of the media files to read or a tuple of the URL and its input option dict.
        :param map: FFmpeg map options
        :param ref_stream: index of the reference stream to pace read operation, defaults to 0. The
                           reference stream is guaranteed to have a frame data on every read operation.
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)

        Note: To read a single stream from a single source, use `audio.read()`, `video.read()` or `image.read()`
              for reducing the overhead

        Specify the streams to return by `map` output option:

            map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

        Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
        'pix_fmt' option is not explicitly set, 'rgb24' is used.

        For audio streams, if 'sample_fmt' output option is not specified, 's16'.
        """

        # initialize FFmpeg argument dict and get input & output information
        args, input_info, ready, output_info, output_args = configure.init_media_read(
            urls, map, {"probesize_in": 32, **options}
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=ready,
            init_deferred_outputs=configure.init_media_read_outputs,
            deferred_output_args=output_args,
            ref_output=ref_stream,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )

        hook = plugins.get_hook()
        self._get_bytes = {"video": hook.video_bytes, "audio": hook.audio_bytes}

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize, self.default_timeout)
        if not any(
            len(self._get_bytes[info["media_type"]](obj=f))
            for f, info in zip(F.values(), self._output_info)
        ):
            raise StopIteration
        return F


class PipedMediaWriter(_EncodedOutputMixin, _RawInputMixin, _PipedFFmpegRunner):

    def __init__(
        self,
        urls: (
            FFmpegOutputUrlComposite
            | list[
                FFmpegOutputUrlComposite
                | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
            ]
        ),
        stream_types: Sequence[Literal["a", "v"]],
        *input_rates_or_opts: *tuple[int | Fraction | FFmpegOptionDict, ...],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        merge_audio_streams: bool | Sequence[int] = False,
        merge_audio_ar: int | None = None,
        merge_audio_sample_fmt: str | None = None,
        merge_audio_outpad: str | None = None,
        overwrite: bool | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Write video and audio data from multiple media streams to one or more files

        :param url: output url
        :param stream_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
        :param input_rates_or_opts: either sample rate (audio) or frame rate (video)
                                     or a dict of input options. The option dict must
                                     include `'ar'` (audio) or `'r'` (video) to specify
                                     the rate.
        :param input_dtypes: list of numpy-style data type strings of input samples
                          or frames of input media streams, defaults to `None`
                          (auto-detect).
        :param input_shapes: list of shapes of input samples or frames of input media
                          streams, defaults to `None` (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
        :param merge_audio_streams: True to combine all input audio streams as a single multi-channel stream. Specify a list of the input stream id's
                                    (indices of `stream_types`) to combine only specified streams.
        :param merge_audio_ar: Sampling rate of the merged audio stream in samples/second, defaults to None to use the sampling rate of the first merging stream
        :param merge_audio_sample_fmt: Sample format of the merged audio stream, defaults to None to use the sample format of the first merging stream
        :param overwrite: True to overwrite existing files, defaults to None (auto-set)
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        if not isinstance(urls, list):
            urls = [urls]

        options = {"probesize_in": 32, **options}
        if overwrite:
            if "n" in options:
                raise FFmpegioError(
                    "cannot specify both `overwrite=True` and `n=ff.FLAG`."
                )
            options["y"] = None

        stream_args = [
            (None, v) if isinstance(v, dict) else (v, None) for v in input_rates_or_opts
        ]
        args, input_info, input_ready, output_info, output_args = (
            configure.init_media_write(
                urls,
                stream_types,
                stream_args,
                merge_audio_streams,
                merge_audio_ar,
                merge_audio_sample_fmt,
                merge_audio_outpad,
                extra_inputs,
                {"probesize_in": 32, **options},
                input_dtypes,
                input_shapes,
            )
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_write_outputs,
            deferred_output_args=output_args,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            blocksize=blocksize,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )


class PipedMediaFilter(_RawOutputMixin, _RawInputMixin, _PipedFFmpegRunner):

    def __init__(
        self,
        expr: str | FilterGraphObject | Sequence[str | FilterGraphObject],
        input_types: Sequence[Literal["a", "v"]],
        *input_rates_or_opts: *tuple[int | Fraction | FFmpegOptionDict, ...],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        ref_output: int = 0,
        output_options: dict[str, FFmpegOptionDict] | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Filter audio/video data streams with FFmpeg filtergraphs

        :param expr: complex filtergraph expression or a list of filtergraphs
        :param input_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
        :param input_rates_or_opts: raw input stream data arguments, each input stream is either a tuple of a sample rate (audio) or frame rate (video) followed by a data blob
                                    or a tuple of a data blob and a dict of input options. The option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
        :param input_dtypes: list of numpy-style data type strings of input samples
                             or frames of input media streams, defaults to `None`
                             (auto-detect).
        :param input_shapes: list of shapes of input samples or frames of input media
                             streams, defaults to `None` (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param ref_output: index or label of the reference stream to pace read operation, defaults to 0.
                           `PipedMediaFilter.read()` operates around the reference stream.
        :param output_options: specific options for keyed filtergraph output pads.
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize (how many reference stream frames/samples to read at once from FFmpeg)
        :                 defaults to `None` to use 1 video frame or 1024 audio frames
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                        will be applied to all input streams unless the option has been already defined in `stream_data`
        """

        input_args = [
            (None, v) if isinstance(v, dict) else (v, None) for v in input_rates_or_opts
        ]

        (
            args,
            input_info,
            input_ready,
            output_info,
            deferred_output_args,
        ) = configure.init_media_filter(
            expr,
            input_types,
            input_args,
            extra_inputs,
            input_dtypes,
            input_shapes,
            {"probesize_in": 32, **options},
            output_options or {},
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_filter_outputs,
            deferred_output_args=deferred_output_args,
            ref_output=ref_output,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )


class PipedMediaTranscoder(_EncodedOutputMixin, _EncodedInputMixin, _PipedFFmpegRunner):
    """Class to transcode encoded media streams"""

    def __init__(
        self,
        input_options: Sequence[FFmpegOptionDict],
        output_options: Sequence[FFmpegOptionDict],
        *,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Encoded media stream transcoder

        :param input_options: FFmpeg input option dicts of all the input pipes. Each dict
                              must contain the `"f"` option to specify the media format.
        :param output_options: FFmpeg output option dicts of all the output pipes. Each dict
                               must contain the `"f"` option to specify the media format.
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param extra_outputs: list of additional output destinations, defaults to None. Each destination
                              may be url string or a pair of a url string and an option dict.
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
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
        """

        args, input_info, output_info = configure.init_media_transcoder(
            [("pipe", opts) for opts in input_options],
            [("pipe", opts) for opts in output_options],
            extra_inputs,
            extra_outputs,
            {"y": None, **options},
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=None,
            init_deferred_outputs=None,
            deferred_output_args=None,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            blocksize=blocksize,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )
