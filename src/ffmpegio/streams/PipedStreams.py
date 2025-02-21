from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import Unpack
from collections.abc import Sequence
from .._typing import Any, ProgressCallable, RawDataBlob
from ..configure import FFmpegInputUrlComposite, FFmpegArgs, FFmpegUrlType, MediaType

import sys
from time import time
from fractions import Fraction
from contextlib import ExitStack

from namedpipe import NPopen

from .. import configure, ffmpegprocess, plugins
from ..threading import LoggerThread, ReaderThread, WriterThread
from ..errors import FFmpegError, FFmpegioError

# fmt:off
__all__ = ["PipedMediaReader"]
# fmt:on


class PipedMediaReader(ExitStack):
    def __init__(
        self,
        *urls: * tuple[
            FFmpegInputUrlComposite | tuple[FFmpegUrlType, dict[str, Any] | None]
        ],
        map: Sequence[str] | dict[str, dict[str, Any] | None] | None = None,
        ref_stream: int = 0,
        blocksize: int | None = None,
        default_timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        queuesize: int | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[dict[str, Any]],
    ):
        """Read video and audio data from multiple media files

        :param *urls: URLs of the media files to read or a tuple of the URL and its input option dict.
        :param map: FFmpeg map options
        :param ref_stream: index of the reference stream to pace read operation, defaults to 0. The
                           reference stream is guaranteed to have a frame data on every read operation.
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)

        Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
            `ffmpegio.video.read()` for each url.

        Specify the streams to return by `map` output option:

            map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

        Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
        'pix_fmt' option is not explicitly set, 'rgb24' is used.

        For audio streams, if 'sample_fmt' output option is not specified, 's16'.
        """

        super().__init__()

        # initialize FFmpeg argument dict and get input & output information
        args, self._input_info, self._output_info = configure.init_media_read(
            urls, map, options
        )

        # create logger without assigning the source stream
        self._logger = LoggerThread(None, show_log)

        # prepare FFmpeg keyword arguments
        self._args = {
            "ffmpeg_args": args,
            "progress": progress,
            "capture_log": True,
            "sp_kwargs": sp_kwargs,
            "on_exit": self._stop_readers,
        }

        # set the default read block size for the referenc stream
        info = self._output_info[ref_stream]
        if blocksize is None:
            blocksize = 1 if info["media_type"] == "video" else 1024
        self.blocksize = blocksize
        self.default_timeout = default_timeout
        self._ref = ref_stream
        self._rates = [v["media_info"][2] for v in self._output_info]
        self._n0 = [0] * len(self._output_info)  # timestamps of the last read sample
        self._pipe_kws = {
            "queue_size": queuesize,
            "update_rate": self._rates[self._ref] / Fraction(blocksize),
        }

        hook = plugins.get_hook()
        self._converters = {"video": hook.bytes_to_video, "audio": hook.bytes_to_audio}
        self._get_bytes = {"video": hook.video_bytes, "audio": hook.audio_bytes}

    def __enter__(self):
        super().__enter__()

        # set up and activate pipes and read/write threads
        self._piped_outputs = configure.init_named_pipes(
            self._args["ffmpeg_args"],
            self._input_info,
            self._output_info,
            self,
            **self._pipe_kws,
        )

        self._n0 = [0] * len(self._output_info)  # timestamps of the last read sample

        # run the FFmpeg
        self._proc = ffmpegprocess.Popen(**self._args)

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

        # wait until all the reader threads are running
        for info in self._output_info:
            info["reader"].wait_till_running()

        return self

    def open(self):
        self.__enter__()

    def __exit__(self, *exc_details):
        try:
            if self._proc is not None and self._proc.poll() is None:
                # kill the ffmpeg runtime
                self._proc.terminate()
                if self._proc.poll() is None:
                    self._proc.kill()
                self._proc = None
        except:
            if not exc_details[0]:
                exc_details = sys.exc_info()
        finally:
            self._logger.join()
            super().__exit__(*exc_details)

    def close(self):
        """Flush and close this stream. This method has no effect if the stream is already
            closed. Once the stream is closed, any read operation on the stream will raise
            a ValueError.

        As a convenience, it is allowed to call this method more than once; only the first call,
        however, will have an effect.

        """

        self.__exit__(None, None, None)

    def specs(self) -> list[str]:
        """list of specifiers of the streams"""

        return [v["user_map"] for v in self._output_info]

    def types(self) -> dict[str, MediaType]:
        """media type associated with the streams (key)"""
        return {v["user_map"]: v["media_type"] for v in self._output_info}

    def rates(self) -> dict[str, int | Fraction]:
        """sample or frame rates associated with the streams (key)"""
        return {v["user_map"]: v["media_info"][2] for v in self._output_info}

    def dtypes(self) -> dict[str, str]:
        """frame/sample data type associated with the streams (key)"""
        return {v["user_map"]: v["media_info"][0] for v in self._output_info}

    def shapes(self) -> dict[str, tuple[int]]:
        """frame/sample shape associated with the streams (key)"""
        return {v["user_map"]: v["media_info"][1] for v in self._output_info}

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

    def _stop_readers(self, returncode):
        # ffmpegprocess on_exit callback function
        for info in self._output_info:
            info["reader"].cool_down()

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self.blocksize, self.default_timeout)
        if not any(
            len(self._get_bytes[info["media_type"]](obj=f))
            for f, info in zip(F.values(), self._output_info)
        ):
            raise StopIteration
        return F

    def readlog(self, n: int = None) -> str:
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

    def read(self, n: int = -1, timeout: float | None = None) -> dict[str, RawDataBlob]:
        """Read and return numpy.ndarray with up to n frames/samples. If
        the argument is omitted or negative, data is read and returned until
        EOF is reached. An empty bytes object is returned if the stream is
        already at EOF.

        If the argument is positive, and the underlying raw stream is not
        interactive, multiple raw reads may be issued to satisfy the byte
        count (unless EOF is reached first). But for interactive raw streams,
        at most one raw read will be issued, and a short result does not
        imply that EOF is imminent.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        # compute the number of frames to read per stream
        if self._n0 and n > 0:
            T = n / self._rates[self._ref]  # duration

            n1 = [(T * r) + n0 for r, n0 in zip(self._rates, self._n0)]
            nread = [int(n1 - n0) for n0, n1 in zip(self._n0, n1)]
            self._n0 = n1
        else:
            nread = [n] * len(self._output_info)
            self._n0 = None

        data = {}
        for info, nr in zip(self._output_info, nread):

            converter = self._converters[info["media_type"]]
            dtype, shape, _ = info["media_info"]
            data[info["user_map"]] = converter(
                b=info["reader"].read(nr, timeout) if nr else b"",
                dtype=dtype,
                shape=shape,
                squeeze=False,
            )

        return data


class PipedWriter: ...


class PipedFilter: ...


class Transcoder:
    """Class to merge multiple media streams in memory

    :param expr: SISO filter graph or None if implicit filtering via output options.
    :type expr: str, None
    :param rate_in: input sample rate
    :type rate_in: int, float, Fraction, str
    :param shape_in: input single-sample array shape, defaults to None
    :type shape_in: seq of ints, optional
    :param dtype_in: input data type string, defaults to None
    :type dtype_in: str, optional
    :param rate: output sample rate, defaults to None (auto-detect)
    :type rate: int, float, Fraction, str, optional
    :param shape: output single-sample array shape, defaults to None
    :type shape: seq of ints, optional
    :param dtype: output data type string, defaults to None
    :type dtype: str, optional
    :param blocksize: read buffer block size in samples, defaults to None
    :type blocksize: int, optional
    :param default_timeout: default filter timeout in seconds, defaults to None (10 ms)
    :type default_timeout: float, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                    defaults to None (no show/capture)

    :type show_log: bool, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional

    """

    def __init__(
        self,
        *input_formats_or_opts: Sequence[str | dict | None],
        nb_inputs: int | None = None,
        output_url: str | None = None,
        blocksize: int | None = None,
        default_timeout: float | None = None,
        progress: Callable | None = None,
        show_log: bool | None = None,
        sp_kwargs: dict | None = None,
        np_kwargs: dict | None = None,
        **output_options: dict[str, Any],
    ) -> None:

        #:float: default filter operation timeout in seconds
        self.default_timeout = default_timeout or 10e-3

        # set this to false in _finalize() if guaranteed for the logger to have output stream info
        self._loggertimeout = True

        nin = len(input_formats_or_opts)
        if nb_inputs is None and not nin:
            raise ValueError(
                "At least one input format/options must be given OR specify nb_inputs."
            )
        if nb_inputs is not None and nin > 0 and nb_inputs != nin:
            raise ValueError(
                "Both nb_inputs and input format/options are given but nb_inputs does not agree with the number of inputs specified."
            )

        inopts = (
            [
                v if isinstance(v, dict) else {} if v is None else {"f": v}
                for v in input_formats_or_opts
            ]
            if len(input_formats_or_opts)
            else [{}] * nb_inputs
        )

        nb_inputs = len(inopts)
        self._input_pipes = inpipes = [
            NPopen("w", **(np_kwargs or {})) for _ in range(nb_inputs)
        ]

        self._output_pipe = None
        if output_url is None:
            self._output_pipe = outpipe = NPopen("r", **(np_kwargs or {}))
            output_url = outpipe.path

        # create input format list
        self._args = ffmpeg_args = configure.empty()
        ffmpeg_args["inputs"].extend([(p.path, o) for p, o in zip(inpipes, inopts)])
        configure.add_url(ffmpeg_args, "output", output_url, output_options)[1][1]

        self._proc = None

        # create the stdin writer without assigning the sink stream
        self._writers = [WriterThread(p, 0) for p in inpipes]

        # create the stdout reader without assigning the source stream
        self._reader = None
        if self._output_pipe is not None:
            self._reader = ReaderThread(self._output_pipe, blocksize, 0)

        # create logger without assigning the source stream
        self._logger = LoggerThread(None, show_log)

        # FFmpeg Popen arguments
        self._cfg = {**sp_kwargs} if sp_kwargs else {}
        self._cfg.update(
            {
                "ffmpeg_args": ffmpeg_args,
                "progress": progress,
                "capture_log": True,
            }
        )

        # start FFmpeg
        self._proc = ffmpegprocess.Popen(**self._cfg)

        self._logger.stderr = self._proc.stderr
        self._logger.start()

        # start the writers
        for writer in self._writers:
            writer.start()

        self._reader.start()
        self._cfg = False

    def close(self):
        """Close the stream.

        This method has no effect if the stream is already closed. Once the
        stream is closed, any read operation on the stream will raise a ThreadNotActive.

        As a convenience, it is allowed to call this method more than once; only the first call,
        however, will have an effect.
        """

        if self._proc is None:
            return

        self._proc.stdout.close()
        self._proc.stderr.close()

        # kill the process
        try:
            self._proc.terminate()
        except:
            pass

        for p in self._input_pipes:
            p.close()

        try:
            self._logger.join()
        except:
            # possibly close before opening the logger thread
            pass
        try:
            self._reader.join()
        except:
            # possibly close before opening the reader thread
            pass
        try:
            for writer in self._writers:
                writer.join()
        except:
            # possibly close before opening the writer thread
            pass

    @property
    def closed(self) -> bool:
        """:bool: True if the stream is closed."""
        return self._proc.poll() is not None

    @property
    def lasterror(self) -> Exception:
        """:FFmpegError: Last error FFmpeg posted"""
        if self._proc.poll():
            return self._logger.Exception()
        else:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def readlog(self, n: int | None = None) -> str:
        """get FFmpeg log lines

        :param n: number of lines to return, defaults to None (every line logged)
        :type n: int, optional
        :return: string containing the requested logs
        :rtype: str

        """
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

    def write(self, stream_id: int, stream_data: bytes, timeout: float | None = None):
        """Run filter operation

        :param data: input data block
        :param timeout: timeout for the operation in seconds, defaults to None

        The input `data` array is expected to have the datatype specified by
        Filter class' `dtype_in` property and the array shape to match Filter
        class' `shape_in` property or with an additional dimension prepended.

        """

        timeout = timeout or self.default_timeout

        timeout += time()

        writer = self._writers[stream_id]
        try:
            writer.write(stream_data, timeout - time())
        except BrokenPipeError as e:
            # TODO check log for error in FFmpeg
            raise e

    def read(self, n: int = -1, timeout: float | None = None) -> bytes:

        try:
            return self._reader.read(n, timeout)
        except AttributeError as e:
            if self._reader is None:
                raise RuntimeError(
                    "read() not supported. FFmpeg is outputting directly to a file"
                )
            raise

    def read_nowait(self, n: int = -1) -> bytes:

        try:
            return self._reader.read_nowait(n)
        except AttributeError as e:
            if self._reader is None:
                raise RuntimeError(
                    "read_nowait() not supported. FFmpeg is outputting directly to a file"
                )
            raise

    def flush(self, timeout: float | None = None):
        """Flush the write buffers of the stream if applicable.

        :param timeout: timeout duration in seconds, defaults to None
        :type timeout: float, optional
        :return: remaining output samples
        :rtype: numpy.ndarray
        """

        timeout = timeout or self.default_timeout

        # If no input, close stdin and read all remaining frames
        y = self._reader.read_all(timeout)
        for p in self._input_pipes:
            p.close()
        self._proc.wait()
        y += self._reader.read_all(None)
