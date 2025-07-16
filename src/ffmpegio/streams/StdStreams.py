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
    FFmpegOptionDict,
    InputSourceDict,
    OutputDestinationDict,
)
from ..configure import (
    FFmpegArgs,
    MediaType,
    InitMediaOutputsCallable,
)
from ..filtergraph.abc import FilterGraphObject
from ..configure import OutputDestinationDict
from contextlib import ExitStack

import sys
from time import time
from fractions import Fraction
from math import prod

from .. import configure, ffmpegprocess, plugins, utils, probe
from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError
from .BaseFFmpegRunner import BaseFFmpegRunner

# fmt:off
__all__ = ["StdAudioDecoder", "StdAudioEncoder", "StdAudioFilter", 
           "StdVideoDecoder", "StdVideoEncoder", "StdVideoFilter", "StdMediaTranscoder"]
# fmt:on


class _StdFFmpegRunner(BaseFFmpegRunner):
    """Base class to run FFmpeg and manage its multiple I/O's"""

    def __init__(
        self,
        *,
        get_num,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict] | None,
        input_ready: bool,
        init_deferred_outputs: InitMediaOutputsCallable | None,
        deferred_output_args: list[FFmpegOptionDict | None],
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

        self._get_num = get_num
        self._input_info = input_info
        self._output_info = output_info
        self._input_ready = input_ready
        self._init_deferred_outputs = init_deferred_outputs
        self._deferred_output_options = deferred_output_args
        self._deferred_data = []

        # all good to go
        self._input_ready = all(input_ready)

        # create logger without assigning the source stream
        self._logger = LoggerThread(None, show_log)

        # prepare FFmpeg keyword arguments
        self._args = {
            "ffmpeg_args": ffmpeg_args,
            "progress": progress,
            "capture_log": True,
            "sp_kwargs": {**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
        }

        # set the default read block size for the referenc stream
        self.default_timeout = default_timeout
        self._pipe_kws = {"queue_size": queuesize}
        self._proc = None
        self._stack = None

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

        if self._input_ready is True:
            self._open(False)

    def _init_std_pipes(self) -> ExitStack:

        return configure.init_std_pipes(
            self._proc.stdin,
            self._proc.stdout,
            self._input_info,
            self._output_info,
            **self._pipe_kws,
        )

    def _write_deferred_data(self):
        pass

    def _close_io(self, _):
        if self._stack:
            self._stack.close()
            self._stack = None

    def _open(self, deferred: bool):

        if deferred:
            # finalize the output configurations
            self._output_info = self._init_deferred_outputs(
                self._args["ffmpeg_args"],
                self._input_info,
                self._deferred_output_options,
                [self._deferred_data],
            )

        # get std pipes
        stdin, stdout, input = configure.assign_std_pipes(
            self._args["ffmpeg_args"], self._input_info, self._output_info
        )

        # run the FFmpeg
        self._proc = ffmpegprocess.Popen(
            **self._args,
            stdin=stdin,
            stdout=stdout,
            input=input,
            on_exit=self._close_io,
        )

        # set up and activate pipes and read/write threads
        self._stack = self._init_std_pipes()

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
            self._proc = None
            self._logger.join()
            self._logger = None

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

    @property
    def closed(self) -> bool:
        """True if the stream is closed."""
        return self._proc.poll() is not None

    @property
    def lasterror(self) -> FFmpegError:
        """Last error FFmpeg posted"""
        if self._proc.poll():
            return self._logger.Exception()
        else:
            return None

    def readlog(self, n: int | None = None) -> str:
        """read FFmpeg log lines

        :param n: number of lines to read
        :return: logged messages
        """
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

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
                if "writer" in info:
                    info["writer"].write(
                        None, None if timeout is None else timeout - time()
                    )

            # wait until the FFmpeg finishes the job
            try:
                self._proc.wait(None if timeout is None else timeout - time())
            except TimeoutError:
                raise
            else:
                rc = self._proc.returncode
                if rc is not None:
                    self._proc = None
        else:
            rc = None
        return rc


from collections.abc import Callable


class _RawInputBaseMixin:

    _get_num: Callable
    _input_info: InputSourceDict
    default_timeout: float | None

    def __init__(self, get_bytes, array_to_opts, **kwargs):
        super().__init__(**kwargs)
        self._get_bytes = get_bytes
        self._array_to_opts = array_to_opts

        # input data must be initially buffered
        self._deferred_data = []
        self._nin = 0

    def _write_deferred_data(self):
        info = self._input_info[0]
        writer = info["writer"]
        for data in self._deferred_data:
            writer.write(data, self.default_timeout)
        self._deferred_data = None
        self._input_ready = True

    @property
    def input_count(self) -> int:
        """number of input frames/samples written"""
        return self._nin

    @property
    def input_rate(self) -> int | Fraction:
        """input sample or frame rates"""
        return self._input_info[0]["raw_info"][2]

    @property
    def input_dtype(self) -> DTypeString:
        """input frame/sample data type"""
        return self._input_info[0]["raw_info"][0]

    @property
    def input_shape(self) -> ShapeTuple:
        """input frame/sample shape"""
        return self._input_info[0]["raw_info"][1]

    @property
    def input_samplesize(self) -> int:
        """input sample/pixel count per frame"""
        return prod(self._input_info[0]["raw_info"][1])

    def write(self, data: RawDataBlob, timeout: float | None = None):
        """write a raw media data

        :param data: audio data blob (depends on the active data conversion plugin)
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is written
                        to the buffer queue


        Write the given NDArray object, data, and return the number
        of bytes written (always equal to the number of data frames/samples,
        since if the write fails an OSError will be raised).

        When in non-blocking mode, a BlockingIOError is raised if the data
        needed to be written to the raw stream but it couldn’t accept all
        the data without blocking.

        The caller may release or mutate data after this method returns,
        so the implementation should only access data during the method call.
        """

        b = self._get_bytes(obj=data)
        self._nin += self._get_num(obj=data)
        if not len(b):
            return

        if data is None:
            raise TypeError("data cannot be None")

        if self._input_ready:
            logger.debug("[writer main] writing...")
            try:
                self._input_info[0]["writer"].write(b, timeout)
            except (BrokenPipeError, OSError):
                self._logger.join_and_raise()
        else:
            # need to collect input data type and shape from the actual data
            # before starting the FFmpeg

            configure.update_raw_input(
                self._args["ffmpeg_args"], self._input_info, 0, data
            )
            self._deferred_data.append(b)
            self._input_ready = True

            # once data is written for all the necessary inputs,
            # analyze them and start the FFmpeg
            self._open(True)


class _AudioInputMixin(_RawInputBaseMixin):

    def __init__(self, **kwargs):
        super().__init__(
            plugins.get_hook().audio_bytes, utils.array_to_audio_options, **kwargs
        )


class _VideoInputMixin(_RawInputBaseMixin):

    def __init__(self, **kwargs):
        super().__init__(
            plugins.get_hook().video_bytes, utils.array_to_video_options, **kwargs
        )


class _EncodedInputMixin:

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

    def _write_deferred_data(self):
        data = self._deferred_data
        info = self._input_info[0]
        if len(data) and "writer" in info:
            info["writer"].write(data, self.default_timeout)
        self._deferred_data = None
        self._input_ready = True

    def write_encoded(self, data: bytes, timeout: float | None = None):
        """write encoded media data to stdout

        :param data: encoded data byte sequence
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is written
                        to the buffer queue
        """

        info = self._input_info[0]

        if self._input_ready:

            try:
                info["writer"].write(data, timeout)
            except:
                raise FFmpegioError("Cannot write to a non-piped input.")

        else:
            # buffer must be contiguous
            data0 = self._deferred_data
            if len(data0):
                data = data0.append(data)
            else:
                self._deferred_data = data

            # need to be able to probe the input streams before starting the FFmpeg
            try:
                probe.format_basic(data)
            except FFmpegError:
                pass  # not ready yet
            else:
                self._input_ready = True

            # once data is written for all the necessary inputs,
            # analyze them and start the FFmpeg
            self._open(True)


class _RawOutputBaseMixin:
    def __init__(self, converter, blocksize, **kwargs):
        super().__init__(**kwargs)
        self._converter = converter

        # set the default read block size for the reference stream
        self._blocksize = blocksize
        self._n0 = None  # timestamps of the last read sample

    @property
    def output_label(self) -> str:
        """FFmpeg/custom label of output stream"""
        return self._output_info[0]["user_map"]

    @property
    def output_type(self) -> MediaType:
        """output media type"""
        return self._output_info[0]["media_type"]

    @property
    def output_rate(self) -> int | Fraction:
        """output sample or frame rates"""
        return self._output_info[0]["raw_info"][2]

    @property
    def output_dtype(self) -> DTypeString:
        """output frame/sample data type"""
        return self._output_info[0]["raw_info"][0]

    @property
    def output_shape(self) -> ShapeTuple:
        """output frame/sample shape"""
        return self._output_info[0]["raw_info"][1]

    @property
    def output_samplesize(self) -> int:
        """output sample/pixel count per frame"""
        return prod(self._output_info[0]["raw_info"][1])

    @property
    def output_count(self) -> int:
        """number of frames/samples read"""
        return self._n0

    def _init_std_pipes(self) -> ExitStack:

        # set the default read block size for the referenc stream
        info = self._output_info[0]
        if self._blocksize is None:
            self._blocksize = 1 if info["media_type"] == "video" else 1024
        self._n0 = 0
        self._pipe_kws = {**self._pipe_kws}

        # set up and activate pipes and read/write threads
        return super()._init_std_pipes()

    def read(self, n: int, timeout: float | None = None) -> RawDataBlob:
        """read output stream

        :param n: number of frames/samples to read. Set -1 to read as many as available.
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

        info = self._output_info[0]
        converter = self._converter
        dtype, shape, _ = info["raw_info"]

        if timeout is None:
            timeout = self.default_timeout

        b = info["reader"].read(n, timeout)
        data = converter(b=b, dtype=dtype, shape=shape, squeeze=False)

        # update the frame/sample counter
        n = self._get_num(obj=data)  # actual number read
        self._n0 += n

        return data


class _AudioOutputMixin(_RawOutputBaseMixin):

    def __init__(self, **kwargs):
        super().__init__(plugins.get_hook().bytes_to_audio, **kwargs)


class _VideoOutputMixin(_RawOutputBaseMixin):

    def __init__(self, **kwargs):
        super().__init__(plugins.get_hook().bytes_to_video, **kwargs)


class _EncodedOutputMixin:
    def __init__(self, blocksize, **kwargs):
        super().__init__(**kwargs)

        # set the default read block size
        self._blocksize = blocksize

    def _init_std_pipes(self) -> ExitStack:

        # set the default read block size for the referenc stream
        self._pipe_kws = {**self._pipe_kws, "blocksize": self._blocksize}

        # set up and activate pipes and read/write threads
        return super()._init_std_pipes()

    def read_encoded(self, n: int, timeout: float | None = None) -> bytes:
        """read encoded data from stdout

        :param n: number of bytes to read, set it to -1 to read as many as available
        :param n: number of frames/samples to read. Set -1 to read as many as available.
        :param timeout: timeout in seconds or defaults to `None` to use the
                        `default_timeout` property. If `default_timeout` is `None`
                        then the operation will block until all the data is read
                        from the buffer queue
        :return: retrieved byte sequence

        Effect of mixing `n` and `timeout`
        ----------------------------------

        ===  =========  =========================================================================
        `n`  `timeout`  Behavior
        ===  =========  =========================================================================
        0    ---        Immediately returns
        >0   `None`     Wait indefinitely until `n` bytes are retrieved
        >0   `float`    Retrieve as much data up to `n` bytes before `timeout` seconds passes
        <0   `None`     Wait indefinitely until FFmpeg terminates
        <0   `float`    Retrieve as much data until `timeout` seconds passes
        ===  =========  =========================================================================
        """

        return self._output_info[0]["reader"].read(n, timeout)


class StdAudioDecoder(_EncodedInputMixin, _AudioOutputMixin, _StdFFmpegRunner):

    def __init__(
        self,
        *,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Decode audio data from media data stream over std pipes

        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        # initialize FFmpeg argument dict and get input & output information
        map = options.pop("map", "0:a:0")
        args, input_info, ready, output_info, output_args = configure.init_media_read(
            ["pipe"], [map], {"probesize_in": 32, **options}
        )

        super().__init__(
            get_num=plugins.get_hook().audio_samples,
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=ready,
            init_deferred_outputs=configure.init_media_read_outputs,
            deferred_output_args=output_args,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )

        self._get_bytes = plugins.get_hook().audio_bytes

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize, self.default_timeout)
        if not len(self._get_bytes(obj=F)):
            raise StopIteration
        return F


class StdVideoDecoder(_EncodedInputMixin, _VideoOutputMixin, _StdFFmpegRunner):

    def __init__(
        self,
        *,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Read audio data from encoded media data stream

        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        # initialize FFmpeg argument dict and get input & output information
        map = options.pop("map", "0:V:0")
        args, input_info, ready, output_info, output_args = configure.init_media_read(
            ["pipe"], [map], {"probesize_in": 32, **options}
        )

        super().__init__(
            get_num=plugins.get_hook().video_frames,
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=ready,
            init_deferred_outputs=configure.init_media_read_outputs,
            deferred_output_args=output_args,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )

        self._get_bytes = plugins.get_hook().video_bytes

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize, self.default_timeout)
        if not len(self._get_bytes(obj=F)):
            raise StopIteration
        return F


class StdAudioEncoder(_EncodedOutputMixin, _AudioInputMixin, _StdFFmpegRunner):

    def __init__(
        self,
        input_rate: int,
        *,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Write video and audio data from multiple media streams to one or more files

        :param rate: input sample rate
        :param input_dtype: numpy-style data type strings of input samples or frames, defaults to `None` (auto-detect).
        :param input_shape: shapes of input samples or frames streams, defaults to `None` (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
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

        args, input_info, input_ready, output_info, output_args = (
            configure.init_media_write(
                ["pipe"],
                "a",
                [(input_rate, None)],
                False,
                None,
                None,
                None,
                extra_inputs,
                {"probesize_in": 32, **options},
                input_dtype,
                input_shape,
            )
        )

        super().__init__(
            get_num=plugins.get_hook().audio_samples,
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


class StdVideoEncoder(_EncodedOutputMixin, _VideoInputMixin, _StdFFmpegRunner):

    def __init__(
        self,
        input_rate: int,
        *,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Write video and audio data from multiple media streams to one or more files

        :param rate: input frame rate
        :param input_dtype: numpy-style data type strings of input samples or frames, defaults to `None` (auto-detect).
        :param input_shape: list of shapes of input samples or frames, defaults to `None` (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
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

        args, input_info, input_ready, output_info, output_args = (
            configure.init_media_write(
                ["pipe"],
                "v",
                [(input_rate, None)],
                False,
                None,
                None,
                None,
                extra_inputs,
                {"probesize_in": 32, **options},
                input_dtype and [input_dtype],
                input_shape and [input_shape],
            )
        )

        super().__init__(
            get_num=plugins.get_hook().video_frames,
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


class StdAudioFilter(_AudioOutputMixin, _AudioInputMixin, _StdFFmpegRunner):

    def __init__(
        self,
        expr: str | FilterGraphObject | Sequence[str | FilterGraphObject],
        input_rate: int,
        *,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Filter audio/video data streams with FFmpeg filtergraphs

        :param expr: filtergraph expression or a list of filtergraphs
        :param input_rate: input sampling rate.
        :param input_dtype: numpy-style data type strings of input samples or frames, defaults to `None` (auto-detect).
        :param input_shape: shapes of input samples or frames, defaults to `None` (auto-detect).
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

        (
            args,
            input_info,
            input_ready,
            output_info,
            deferred_output_args,
        ) = configure.init_media_filter(
            expr,
            "a",
            [(input_rate, None)],
            None,
            input_dtype and [input_dtype],
            input_shape and [input_shape],
            {"probesize_in": 32, **options},
            {},
        )

        super().__init__(
            get_num=plugins.get_hook().audio_samples,
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_filter_outputs,
            deferred_output_args=deferred_output_args,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )

    def filter(
        self, data: RawDataBlob, timeout: float | None = None
    ) -> RawDataBlob | None:
        """Run filter operation

        :param data: input data block
        :type data: numpy.ndarray
        :param timeout: timeout for the operation in seconds, defaults to None
        :type timeout: float, optional
        :return: output data block
        :rtype: numpy.ndarray

        The input `data` array is expected to have the datatype specified by
        Filter class' `input_dtype` property and the array shape to match Filter
        class' `input_shape` property or with an additional dimension prepended.

        .. important::
          If `timeout = None`, the read operation is non-blocking. There is at
          least 32-frame latency is imposed by FFmpeg, so the initial few frames
          will not produce any output.

        """

        timeout = timeout or self.default_timeout
        if timeout:
            timeout += time()

        self.write(data, timeout and timeout - time())
        return self.read(self._get_num(obj=data), (timeout and timeout - time()) or 0)


class StdVideoFilter(_VideoOutputMixin, _VideoInputMixin, _StdFFmpegRunner):

    def __init__(
        self,
        expr: str | FilterGraphObject | Sequence[str | FilterGraphObject],
        input_rate: int | Fraction,
        *,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
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
        :param input_rate: frame rate
        :param input_dtype: numpy-style data type strings of input samples or frames, defaults to `None` (auto-detect).
        :param input_shape: shapes of input samples or frames , defaults to `None` (auto-detect).
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

        (
            args,
            input_info,
            input_ready,
            output_info,
            deferred_output_args,
        ) = configure.init_media_filter(
            expr,
            "v",
            [(input_rate, None)],
            None,
            input_dtype and [input_dtype],
            input_shape and [input_shape],
            {"probesize_in": 32, **options},
            {},
        )

        super().__init__(
            get_num=plugins.get_hook().video_frames,
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_filter_outputs,
            deferred_output_args=deferred_output_args,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )

    def filter(
        self, data: RawDataBlob, timeout: float | None = None
    ) -> RawDataBlob | None:
        """Run filter operation

        :param data: input data block
        :type data: numpy.ndarray
        :param timeout: timeout for the operation in seconds, defaults to None
        :type timeout: float, optional
        :return: output data block
        :rtype: numpy.ndarray

        The input `data` array is expected to have the datatype specified by
        Filter class' `input_dtype` property and the array shape to match Filter
        class' `input_shape` property or with an additional dimension prepended.

        .. important::
          If `timeout = None`, the read operation is non-blocking. There is at
          least 32-frame latency is imposed by FFmpeg, so the initial few frames
          will not produce any output.

        """

        timeout = timeout or self.default_timeout
        if timeout:
            timeout += time()

        self.write(data, timeout and timeout - time())
        return self.read(self._get_num(obj=data), (timeout and timeout - time()) or 0)


class StdMediaTranscoder(_EncodedOutputMixin, _EncodedInputMixin, _StdFFmpegRunner):
    """Class to transcode one media stream to another via std pipes"""

    def __init__(
        self,
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
            [("pipe", {})],
            [("pipe", {})],
            extra_inputs,
            extra_outputs,
            {"y": None, **options},
        )

        super().__init__(
            get_num=None,
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=True,
            init_deferred_outputs=None,
            deferred_output_args=None,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            blocksize=blocksize,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )
