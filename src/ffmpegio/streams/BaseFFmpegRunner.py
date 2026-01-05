from __future__ import annotations

import logging
import sys
from time import time
from contextlib import ExitStack
from enum import IntEnum

from .. import ffmpegprocess, configure, utils

from .._typing import (
    Any,
    Literal,
    Iterable,
    Callable,
    RawDataBlob,
    ProgressCallable,
    InputInfoDict,
    OutputInfoDict,
    InputPipeInfoDict,
    OutputPipeInfoDict,
)

from ..configure import FFmpegArgs
from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError

logger = logging.getLogger("ffmpegio")

__all__ = ["BaseFFmpegRunner"]


class BaseFFmpegRunner:
    """Base class to run FFmpeg and manage its multiple I/O's"""

    class Status(IntEnum):
        NOTHING_SET = 0
        ARGUMENTS_SET = 1
        PIPES_SET = 2
        RUNNING = 3
        STOPPED = 4

    probesize: int = 64 * 1024
    default_timeout: float | None = None
    _args: dict[str, Any]

    _init_func: Callable
    _init_kws: dict

    _nb_inputs: tuple[int, int] = (0, 0)  # (raw, raw+encoded)
    _piped_inputs: dict[int, Literal["input_urls", "input_stream_args", "extra_input"]]
    _piped_inputs_buffer: dict[int, bytes | list[RawDataBlob]]
    _piped_inputs_avail: int = 0

    _input_info: list[InputInfoDict]
    _output_info: list[OutputInfoDict]
    _input_pipes: dict[int, InputPipeInfoDict] | None = None
    _output_pipes: dict[int, OutputPipeInfoDict] | None = None

    _status: Status = Status.NOTHING_SET

    _proc: ffmpegprocess.Popen
    _stack: ExitStack
    _logger: LoggerThread

    def __init__(
        self,
        init_func: Callable,
        init_kws: dict,
        default_timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        probesize: int | None = None,
    ):
        """Base FFmpeg runner

        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        init_kws["options"] = {"probesize_in": probesize, **init_kws["options"]}

        self._init_func = staticmethod(init_func)
        self._init_kws = init_kws

        self._stack: ExitStack = ExitStack()

        # create logger without assigning the source stream
        self._logger = LoggerThread(None, bool(show_log))

        # prepare FFmpeg keyword arguments
        self._args = {
            "progress": progress,
            "capture_log": True,
            "sp_kwargs": sp_kwargs,
        }
        if overwrite is not None:
            self._args["overwrite"] = overwrite

        # set the default read block size for the reference stream
        if default_timeout is not None:
            self.default_timeout = default_timeout

        if probesize is not None:
            self.probesize = int(probesize)

        self._piped_inputs = {}
        self._piped_inputs_buffer = {}

    def _analyze_inputs(self):
        """identify which input init_fun keyword arguments require data from pipe"""
        kws = self._init_kws
        pipes = self._piped_inputs
        if "input_urls" in kws:
            # encoded: list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
            for i, (url, _) in enumerate(kws["input_urls"]):
                if utils.is_pipe(url):
                    pipes[i] = "input_urls"
            self._nb_inputs = (0, len(kws["input_urls"]))
        if "input_stream_args" in kws:
            # raw: list[tuple[RawDataBlob, FFmpegOptionDict]]
            n_in = len(kws["input_stream_args"])
            for i in range(n_in):
                pipes[i] = "input_stream_args"
            if "extra_input" in kws:
                # encoded:list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
                for i, (url, _) in enumerate(kws["extra_input"]):
                    if utils.is_pipe(url):
                        pipes[i + n_in] = "extra_input"
            self._nb_inputs = (n_in, n_in + len(kws["extra_input"]))

    def _put_aside_input(
        self, stream: int, data: RawDataBlob | bytes
    ) -> bytes | RawDataBlob | None:
        """write data to a buffer prior to running ffmpeg

        :param stream: input stream id, index to self._input_info
        :param data: data blob if raw media data or bytes if encoded data
        :returns: the first data blob of the raw stream or all received bytes of
                  encoded stream (repeats every time) or None if no new data

        If ffprobe analysis is necessary to configure the FFmpeg arguments,
        every input pipe must be filled with the first batch of data. This
        function is to be called from a write function to sets pre-run written
        data aside.

        if it contains data for a new stream, attempts to configure ffmpeg args
        """

        assert stream < self._nb_inputs[1]
        assert self._status == self._status.NOTHING_SET

        if stream in self._piped_inputs_buffer:
            buf = self._piped_inputs_buffer[stream]
            if isinstance(data, bytes):
                assert isinstance(buf, bytes)
                self._piped_inputs_buffer[stream] = buf = buf + data
                return buf

            else:
                assert not isinstance(buf, bytes)
                self._piped_inputs_buffer[stream].append(data)

        else:  # first write -> update the kws
            self._piped_inputs_buffer[stream] = (
                data if isinstance(data, bytes) else [data]
            )
            self._piped_inputs_avail = self._piped_inputs_avail + 1
            return data

        return None

    def _try_config_ffmpeg(
        self, stream: int = -1, data: bytes | RawDataBlob | None = None
    ) -> bool:
        """Configure FFmpeg options"""

        if self._status != self._status.NOTHING_SET:
            raise FFmpegioError("FFmpeg options have already been configured.")

        if stream >= 0 and data is not None:
            # load the new data blob/bytes to the respective keyword argument
            kw_name = self._piped_inputs[stream]
            i = stream - self._nb_inputs[0] if kw_name == "extra_input" else stream
            self._init_kws[kw_name][i] = (data, self._init_kws[kw_name][i][1])

        kws = self._init_kws

        try:
            ffmpeg_args, input_info, output_info = self._init_func(**kws)
        except:
            return False

        self._args["ffmpeg_args"] = ffmpeg_args
        self._input_info = input_info
        self._output_info = output_info

        self._status = self._status.ARGUMENTS_SET

        return True

    def _init_pipes(self, use_std_pipes: bool):
        # set up and activate standard pipes and read/write threads
        # configure named pipes

        if self._status != self._status.ARGUMENTS_SET:
            if self._status < self._status.ARGUMENTS_SET:
                raise FFmpegioError(
                    "FFmpeg configuration not set. Run `config_ffmpeg()` first."
                )
            raise FFmpegioError("FFmpeg pipes have already configured.")

        args = self._args["ffmpeg_args"]
        more_args = {}
        input_pipes = {}
        output_pipes = {}

        if len(self._input_info):
            input_pipes, more_args = configure.assign_input_pipes(
                args, self._input_info, use_std_pipes
            )

        if len(self._output_info):
            output_pipes, sp_kwargs = configure.assign_output_pipes(
                args, self._output_info, use_std_pipes
            )
            more_args.update(sp_kwargs)

        self._stack = configure.init_named_pipes(
            input_pipes, output_pipes, self._input_info, self._output_info
        )

        self._input_pipes = input_pipes
        self._output_pipes = output_pipes
        self._args.update(more_args)
        self._status = self._status.PIPES_SET

    def _on_exit(self, rc):
        if self._status.RUNNING:
            self._stack.close()
            self._status = self._status.STOPPED

    def _run_ffmpeg(self):

        if self._status != self._status.PIPES_SET:
            if self._status < self._status.PIPES_SET:
                raise FFmpegioError(
                    "FFmpeg configuration not set. Run `config_ffmpeg()` first."
                )
            raise FFmpegioError("FFmpeg pipes have already configured.")

        # run the FFmpeg
        try:
            self._status = self._status.RUNNING
            self._proc = ffmpegprocess.Popen(**self._args, on_exit=self._on_exit)
        except:
            if self._stack is not None:
                self._stack.close()
            raise

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

    def _write_from_buffer(self):
        # remove the data from the init keyword args
        for st, kw in self._piped_inputs.items():
            i = st - self._nb_inputs[0] if kw == "extra_input" else st
            self._init_kws[kw][i] = ("-", self._init_kws[kw][i][1])

            buf = self._piped_inputs_buffer[buf]
            if isinstance(buf, bytes):
                self._input_pipes[i]["writer"].write(buf)
            else:
                for frame in buf:
                    self._input_pipes[i]["writer"].write(frame)

            del self._piped_inputs_buffer[buf]

    def _terminate(self):
        """Kill FFmpeg process and close the streams"""

        if self._proc is not None and self._proc.poll() is None:
            # kill the ffmpeg runtime
            self._proc.terminate()
            if self._proc.poll() is None:
                self._proc.kill()

            self._logger.join()

    def start(self):
        """start FFmpeg processing

        Note
        ----

        It may flag to defer starting the FFmpeg process if the input streams
        are not fully specified and must wait to deduce them from the written
        data.

        """

        if self._input_ready is True or all(self._input_ready):
            self._open(False)

    def close(self):
        """Kill FFmpeg process and close the streams"""

        if self._proc is not None and self._proc.poll() is None:
            # kill the ffmpeg runtime
            self._proc.terminate()
            if self._proc.poll() is None:
                self._proc.kill()

            self._logger.join()

    def __enter__(self):

        self.open()
        return self

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

            # std pipe, no threading, flush and close the stdin
            if self._proc.stdin is not None:
                self._proc.stdin.flush()
                self._proc.stdin.close()

            # write the sentinel to each input queue
            for pinfo in self._input_pipes.values():
                pinfo["writer"].write(
                    None, None if timeout is None else timeout - time()
                )

            # wait until the FFmpeg finishes the job
            self._proc.wait(None if timeout is None else timeout - time())

            rc = self._proc.returncode
            if rc is not None:
                self._proc = None
        else:
            rc = None
        return rc

    # def _write_raw(self, stream: int, data: RawDataBlob):
    #     info = self._input_pipes[stream]
    #     info["writer"].write(data)

    # def _write_enc(self, stream: int, data: bytes):
    #     info = self._input_pipes[stream]
    #     info["writer"].write(data)

    # def _read_raw(self, stream: int, n: int, timeout: float | None) -> RawDataBlob:
    #     info = self._output_pipes[stream]
    #     return info["reader"].read(n, timeout or self.default_timeout)

    # def _read_enc(self, stream: int, n: int, timeout: float | None) -> bytes:
    #     info = self._output_pipes[stream]
    #     return info["reader"].read(n, timeout or self.default_timeout)
