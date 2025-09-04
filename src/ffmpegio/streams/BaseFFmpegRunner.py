from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import Literal
from .._typing import (
    ProgressCallable,
    InputSourceDict,
    OutputDestinationDict,
    FFmpegOptionDict,
)
from ..configure import FFmpegArgs, InitMediaOutputsCallable
from contextlib import ExitStack

import sys
from time import time

from .. import ffmpegprocess
from ..threading import LoggerThread
from ..errors import FFmpegError

__all__ = ["BaseFFmpegRunner"]


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
                if "writer" in info: # has writer thread
                    info["writer"].write(
                        None, None if timeout is None else timeout - time()
                    )
                else: # std pipe, no threading
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
