from __future__ import annotations

import logging

import sys
from time import time
from collections.abc import Sequence
from contextlib import ExitStack
from fractions import Fraction

from typing_extensions import Callable, Literal

from .. import configure, plugins, utils, probe, ffmpegprocess

from .._typing import (
    ProgressCallable,
    InputSourceDict,
    OutputDestinationDict,
    FFmpegOptionDict,
    RawDataBlob,
    ShapeTuple,
    DTypeString,
    MediaType,
)

from ..configure import FFmpegArgs, MediaType, InitMediaOutputsCallable
from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError
from ..plugins.hookspecs import FromBytesCallable, CountDataCallable, ToBytesCallable
from .._utils import get_bytesize

logger = logging.getLogger("ffmpegio")

__all__ = [
    "BaseFFmpegRunner",
    "EncodedInputsMixin",
    "RawOutputsMixin",
    "EncodedOutputsMixin",
    "RawInputMixin",
    "EncodedInputMixin",
    "RawOutputMixin",
    "EncodedOutputMixin",
]


class BaseFFmpegRunner:
    """Base class to run FFmpeg and manage its multiple I/O's"""

    default_timeout: float | None = None
    _proc: ffmpegprocess.Popen

    def __init__(
        self,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict],
        input_ready: Literal[True] | list[bool],
        init_deferred_outputs: InitMediaOutputsCallable | None,
        deferred_output_args: list[FFmpegOptionDict | None],
        default_timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        **_,
    ):
        """Base FFmpeg runner

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg output option dicts of all the output pipes. Each dict
                               must contain the `"f"` option to specify the media format.
        :param output_info: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param input_ready: True to start FFmpeg, if not provide a list of per-stream readiness
        :param init_deferred_outputs: function to initialize the outputs which have been deferred to
                                      configure until the first batch of input data is in
        :param deferred_output_args:
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
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

        self._stack: ExitStack = ExitStack()
        self._input_info = input_info
        self._output_info = output_info
        self._input_ready = input_ready
        self._init_deferred_outputs = init_deferred_outputs
        self._deferred_output_options = deferred_output_args
        self._deferred_data = []

        # create logger without assigning the source stream
        self._logger = LoggerThread(None, bool(show_log))

        # prepare FFmpeg keyword arguments
        self._args = {
            "ffmpeg_args": ffmpeg_args,
            "progress": progress,
            "capture_log": True,
            "sp_kwargs": sp_kwargs,
        }
        if overwrite is not None:
            self._args["overwrite"] = overwrite

        # set the default read block size for the reference stream
        if default_timeout is not None:
            self.default_timeout = default_timeout

    def __enter__(self):

        self.open()
        return self

    def open(self):
        """start FFmpeg processing

        Note
        ----

        It may flag to defer starting the FFmpeg process if the input streams
        are not fully specified and must wait to deduce them from the written
        data.

        """

        if self._input_ready is True or all(self._input_ready):
            self._open(False)

    def _assign_pipes(self):
        """assign pipes (pre-popen)"""
        pass

    def _init_pipes(self):
        """initialize pipes (post-popen)"""
        pass

    def _write_deferred_data(self):
        pass

    def _open(self, deferred: bool):

        logger.info("starting FFmpeg subprocess")

        if deferred:

            assert self._init_deferred_outputs is not None

            # finalize the output configurations
            self._output_info = self._init_deferred_outputs(
                self._args["ffmpeg_args"],
                self._input_info,
                self._deferred_output_options,
                self._deferred_data,
            )

        # set up and activate named pipes and read/write threads
        self._assign_pipes()

        # run the FFmpeg
        try:
            self._proc = ffmpegprocess.Popen(
                **self._args, on_exit=(lambda _: self._stack.close())
            )
        except:
            if self._stack is not None:
                self._stack.close()
            raise

        # set up and activate standard pipes and read/write threads
        self._init_pipes()

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

        # if any pending data, queue them
        if deferred:
            self._write_deferred_data()

        return self

    def close(self):
        """Kill FFmpeg process and close the streams"""

        if self._proc is not None and self._proc.poll() is None:
            # kill the ffmpeg runtime
            self._proc.terminate()
            if self._proc.poll() is None:
                self._proc.kill()

            self._logger.join()

    def __exit__(self, *exc_details) -> bool:
        try:
            self.close()
            return False
        except:
            if not exc_details[0]:
                exc_details = sys.exc_info()
        finally:
            try:
                self._logger.join()
            except RuntimeError:
                pass
        return False

    @property
    def closed(self) -> bool:
        """True if the stream is closed."""
        return self._proc is None or self._proc.poll() is not None

    @property
    def lasterror(self) -> FFmpegError | None:
        """Last error FFmpeg posted"""
        if self._proc and self._proc.poll():
            return self._logger and self._logger.Exception
        else:
            return None

    def readlog(self, n: int | None = None) -> str:
        """read FFmpeg log lines

        :param n: number of lines to read or None to read all currently found in the buffer
        :return: logged messages
        """

        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs if n is None else self._logger.logs[:n])

    def wait(self, timeout: float | None = None) -> int | None:
        """close all input pipes and wait for FFmpeg to exit

        :param timeout: a timeout for blocking in seconds, or fractions
                        thereof, defaults to None, to wait indefinitely
        :raise `TimeoutExpired`: if a timeout is set, and the process does not
                                 terminate after timeout seconds. It is safe to
                                 catch this exception and retry the wait.
        :return returncode: return subprocess Popen returncode attribute
        """

        if timeout is None:
            timeout = self.default_timeout

        if self._proc:

            if timeout is not None:
                timeout += time()

            # write the sentinel to each input queue
            for info in self._input_info:
                if "writer" in info:  # has writer thread
                    info["writer"].write(
                        None, None if timeout is None else timeout - time()
                    )
                else:  # std pipe, no threading
                    # close the stdout
                    self._proc.stdin.close()

            # wait until the FFmpeg finishes the job
            self._proc.wait(None if timeout is None else timeout - time())

            rc = self._proc.returncode
            if rc is not None:
                self._proc = None
        else:
            rc = None
        return rc


class BaseRawInputsMixin:
    """write a raw media data to a specified stream (backend)"""

    default_timeout: float | None
    _input_info: list[InputSourceDict]
    _output_info: list[OutputDestinationDict]
    _deferred_data: list[list[bytes]]
    _input_ready: Literal[True] | list[bool]
    _logger: LoggerThread | None
    _open: Callable[[bool], None]
    _args: dict

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # input data must be initially buffered
        self._deferred_data = [[] for _ in range(len(self._input_info))]

    def _write_deferred_data(self):
        for src, info in zip(self._deferred_data, self._input_info):
            if "writer" in info and len(src):
                writer = info["writer"]
                for data in src:
                    writer.write(data, self.default_timeout)
        self._deferred_data = []
        self._input_ready = True

    def _write_stream_bytes(
        self,
        converter: ToBytesCallable,
        stream_id: int,
        data: RawDataBlob,
        timeout: float | None,
    ):
        """write a raw media data to a specified stream (backend)"""

        b = converter(obj=data)
        if not len(b):
            return

        if self._input_ready is True:
            logger.debug("[writer main] writing...")

            try:
                self._input_info[stream_id]["writer"].write(b, timeout)
            except (KeyError, BrokenPipeError, OSError):
                if self._logger:
                    self._logger.join_and_raise()

        else:
            # need to collect input data type and shape from the actual data
            # before starting the FFmpeg

            configure.update_raw_input(
                self._args["ffmpeg_args"], self._input_info, stream_id, data
            )

            self._deferred_data[stream_id].append(b)
            self._input_ready[stream_id] = True

            if all(self._input_ready):
                # once data is written for all the necessary inputs,
                # analyze them and start the FFmpeg
                self._open(True)

    @property
    def input_types(self) -> dict[int, MediaType | None]:
        """media type associated with the input streams"""
        return {i: v.get("media_type", None) for i, v in enumerate(self._input_info)}

    @property
    def input_rates(self) -> dict[int, int | Fraction | None]:
        """sample or frame rates associated with the input streams"""
        return {
            i: v["raw_info"][2] if "raw_info" in v else None
            for i, v in enumerate(self._input_info)
        }

    @property
    def input_dtypes(self) -> dict[int, DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""
        return {
            i: v["raw_info"][0] if "raw_info" in v else None
            for i, v in enumerate(self._input_info)
        }

    @property
    def input_shapes(self) -> dict[int, ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""
        return {
            i: v["raw_info"][1] if "raw_info" in v else None
            for i, v in enumerate(self._input_info)
        }


class BaseEncodedInputsMixin:

    # FFmpegRunner's properties accessed
    default_timeout: float | None
    _input_info: list[InputSourceDict]
    _output_info: list[OutputDestinationDict]
    _deferred_data: list[list[bytes]]
    _input_ready: Literal[True] | list[bool]
    _logger: LoggerThread | None
    _open: Callable[[bool], None]

    def _write_deferred_data(self):
        for data, info in zip(self._deferred_data, self._input_info):
            if len(data) and "writer" in info:
                info["writer"].write(data, self.default_timeout)
        self._deferred_data = []
        self._input_ready = True

    def _write_encoded_stream(
        self,
        index: int,
        info: OutputDestinationDict,
        data: bytes,
        timeout: float | None,
    ):
        """write a raw media data to a specified stream (backend)"""

        if self._input_ready is True:
            try:
                info["writer"].write(data, timeout)
            except:
                raise FFmpegioError("Cannot write to a non-piped input.")

        else:

            # buffer must be contiguous
            data0 = self._deferred_data[index]
            if len(data0):
                data0.append(data)

            else:
                self._deferred_data[index] = [data]

            # need to be able to probe the input streams before starting the FFmpeg
            try:
                probe.format_basic(data)
            except FFmpegError:
                pass  # not ready yet
            else:
                self._input_ready[index] = True

            if all(self._input_ready):
                # once data is written for all the necessary inputs,
                # analyze them and start the FFmpeg
                self._open(True)


class BaseRawOutputsMixin:

    default_timeout: float | None
    _input_info: list[InputSourceDict]
    _output_info: list[OutputDestinationDict]
    _deferred_data: list[list[bytes]]
    _input_ready: bool
    _logger: LoggerThread | None

    def __init__(self, blocksize, ref_output, **kwargs):
        super().__init__(**kwargs)

        # set the default read block size for the reference stream
        self._blocksize = blocksize
        self._ref = ref_output
        self._rates = None
        self._n0 = None  # timestamps of the last read sample

    @property
    def output_labels(self) -> list[str | None]:
        """FFmpeg/custom labels of output streams"""
        return [
            v.get("user_map", None) or f"{i}" for i, v in enumerate(self._output_info)
        ]

    @property
    def output_types(self) -> list[MediaType | None]:
        """media type associated with the output streams (key)"""
        return [v["media_type"] for v in self._output_info]

    @property
    def output_rates(self) -> list[int | Fraction | None]:
        """sample or frame rates associated with the output streams (key)"""

        def get_rate(v):
            return v and v[2]

        return [get_rate(v) for v in self._output_info]

    @property
    def output_dtypes(self) -> list[DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""

        def get_dtype(v):
            return v and v[1]

        return [get_dtype(v) for v in self._output_info]

    @property
    def output_shapes(self) -> list[ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""

        def get_shape(v):
            return v and v[0]

        return [get_shape(v) for v in self._output_info]

    @property
    def output_counts(self) -> list[int]:
        """number of frames/samples read"""
        return [0] * len(self._output_info) if self._n0 is None else list(self._n0)

    def _init_pipes(self) -> ExitStack:

        # set the default read block size for the referenc stream
        info = self._output_info[self._ref]
        if self._blocksize is None:
            self._blocksize = 1 if info["media_type"] == "video" else 1024
        self._rates = self.output_rates

        if any(r is None for r in self._rates):
            raise FFmpegioError("There is an output stream without known output rate.")

        self._n0 = [0] * len(self._output_info)  # timestamps of the last read sample
        self._pipe_kws = {
            **self._pipe_kws,
            "update_rate": self._rates[self._ref] / Fraction(self._blocksize),
        }

        # set up and activate pipes and read/write threads
        return super()._init_pipes()

    def _read_stream_bytes(
        self,
        converter: FromBytesCallable,
        counter: CountDataCallable,
        dtype: DTypeString,
        shape: ShapeTuple,
        info: OutputDestinationDict,
        stream_id: int | str,
        n: int,
        timeout: float | None = None,
        squeeze: bool = False,
    ) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        data = converter(
            b=info["reader"].read(n, timeout), dtype=dtype, shape=shape, squeeze=squeeze
        )

        # update the frame/sample counter
        n = counter(obj=data)  # actual number read
        self._n0[stream_id] += n

        return data


class BaseEncodedOutputsMixin:

    default_timeout: float | None
    _input_info: list[InputSourceDict]
    _output_info: list[OutputDestinationDict]
    _deferred_data: list[list[bytes]]
    _input_ready: bool
    _logger: LoggerThread

    def __init__(self, blocksize, **kwargs):
        super().__init__(**kwargs)

        # set the default read block size
        self._blocksize = blocksize

    def _init_pipes(self) -> ExitStack:

        # set the default read block size for the referenc stream
        self._pipe_kws = {**self._pipe_kws, "blocksize": self._blocksize}

        # set up and activate pipes and read/write threads
        return super()._init_pipes()

    def _read_encoded_stream(
        self,
        info: OutputDestinationDict,
        n: int,
        timeout: float | None = None,
    ) -> bytes:
        """read selected output stream (shared backend)"""

        return info["reader"].read(n, timeout)


class RawInputsMixin(BaseRawInputsMixin):

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

class RawInputMixin(BaseRawInputsMixin):

    _media_bytes = {"video": "video_bytes", "audio": "audio_bytes"}
    _array_to_opts = {
        "video": utils.array_to_video_options,
        "audio": utils.array_to_audio_options,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        hook = plugins.get_hook()
        info = self._input_info[0]
        self._get_bytes = {"video": hook.video_bytes, "audio": hook.audio_bytes}

        # input data must be initially buffered
        self._deferred_data = [[] for _ in range(len(self._input_info))]

    def write(
        self, data: RawDataBlob, timeout: float | None = None
    ):
        """write a raw media data to a specified stream

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
            info = self._input_info[0]
        except IndexError:
            raise FFmpegioError("stream_id=0 is an invalid input stream index.")

        if timeout is None:
            timeout = self.default_timeout

        media_type = info["media_type"]
        self._write_stream_bytes(self._get_bytes[media_type], 0, data, timeout)


class EncodedInputsMixin(BaseEncodedInputsMixin):

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


class RawOutputsMixin(BaseRawOutputsMixin):
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


class EncodedOutputsMixin(BaseEncodedOutputsMixin):

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

class EncodedOutputMixin(BaseEncodedOutputsMixin):

    def read_encoded(
        self, n: int, timeout: float | None = None
    ) -> bytes:
        """read encoded output stream

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
        stream_id = utils.get_output_stream_id(info, 0)
        return self._read_encoded_stream(info[stream_id], n, timeout)


#############################


class EncodedInputMixin(BaseEncodedInputsMixin):

    def write_encoded(self, data: bytes, timeout: float | None = None):
        """write a raw media data to a specified stream

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
            info = self._input_info[0]
        except IndexError:
            raise FFmpegioError("stream_id=0 is an invalid input stream index.")

        if timeout is None:
            timeout = self.default_timeout

        self._write_encoded_stream(0, info, data, timeout)


class RawOutputMixin(BaseRawOutputsMixin):
    def __init__(self, blocksize, **kwargs):
        super().__init__(blocksize=blocksize, ref_output=0, **kwargs)
        hook = plugins.get_hook()
        info = self._input_info[0]
        self._converter = {"video": hook.bytes_to_video, "audio": hook.bytes_to_audio}[
            info["media_type"]
        ]
        self.converter = self._converter
        self._get_num = {"video": hook.video_frames, "audio": hook.audio_samples}[
            info["media_type"]
        ]

    def read(self, n: int, timeout: float | None = None) -> RawDataBlob:
        """read selected output stream

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

        info = self._output_info[0]
        converter = self._converter
        counter = self._get_num
        dtype, shape, _ = info["raw_info"]

        return self._read_stream_bytes(
            converter, counter, dtype, shape, info, 0, n, timeout, squeeze=False
        )

    @property
    def output_label(self) -> str | None:
        """FFmpeg/custom labels of output streams"""
        return self._output_info[0].get("user_map", None)

    @property
    def output_type(self) -> MediaType | None:
        """media type associated with the output streams (key)"""
        return self._output_info[0]["media_type"]

    @property
    def output_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][2] if "raw_info" in info else None

    @property
    def output_dtype(self) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][0] if "raw_info" in info else None

    @property
    def output_shape(self) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][1] if "raw_info" in info else None

    @property
    def output_count(self) -> int:
        """number of frames/samples read"""
        return 0 if self._n0 is None else self._n0[0]

    @property
    def output_bytesize(self) -> int | None:
        """number of bytes per output sample/pixel"""
        return get_bytesize(self.output_shape, self.output_dtype)

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize)
        if plugins.get_hook().is_empty(obj=F):
            raise StopIteration
        return F
