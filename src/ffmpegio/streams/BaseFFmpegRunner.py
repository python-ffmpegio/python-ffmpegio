from __future__ import annotations

import logging
import sys
from contextlib import ExitStack
from enum import IntEnum
from fractions import Fraction
from functools import cached_property
from abc import ABCMeta, abstractmethod

from .. import ffmpegprocess, configure, utils, stream_spec

from .._typing import (
    Any,
    Literal,
    Callable,
    Iterator,
    MediaType,
    RawDataBlob,
    ProgressCallable,
    InputInfoDict,
    OutputInfoDict,
    InputPipeInfoDict,
    OutputPipeInfoDict,
)

from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError, FFmpegioInsufficientInputData

logger = logging.getLogger("ffmpegio")

__all__ = ["BaseFFmpegRunner"]


class FFmpegStatus(IntEnum):
    NOTHING_SET = 0
    BUFFERING = 1
    ARGUMENTS_SET = 2
    PIPES_SET = 3
    RUNNING = 4
    STOPPED = 5


class InitMediaKeywordsWithInputBuffer(dict):
    """class to buffer FFmpeg input data before running it to probe configuration information"""

    # pre-analysis/buffering variables
    _nraw = 0
    _raw_pipe_buffer: None | list[list[RawDataBlob] | None]  # for 'input_stream_args'
    _enc_pipe_buffer: dict[int, bytes | None]  # for 'input_urls' or 'extra_inputs'

    def __init__(self, init_kws: dict):
        """identify which input init_fun keyword arguments require data from pipe"""
        super().__init__(init_kws)
        self._raw_input = "input_stream_args" in self
        self._enc_pipe_buffer = {}
        self._raw_pipe_buffer = None

        # analyze the keywords and replace items to be tweaked
        if self._raw_input:
            # raw: list[tuple[RawDataBlob, FFmpegOptionDict]]
            self["input_stream_args"] = [*self["input_stream_args"]]

            self._nraw = len(self["input_stream_args"])
            self._raw_pipe_buffer = [None] * self._nraw

            if "extra_inputs" in self:
                # encoded:list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
                self["extra_inputs"] = [*self["extra_inputs"]]

                for i, (url, _) in enumerate(self["extra_inputs"]):
                    if utils.is_pipe(url):
                        self._enc_pipe_buffer[i] = b""

        else:
            # encoded: list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
            self["input_urls"] = [*self["input_urls"]]

            for i, (url, _) in enumerate(self["input_urls"]):
                if utils.is_pipe(url):
                    self._enc_pipe_buffer[i] = None

    def put_data(self, stream: int, data: RawDataBlob | bytes) -> bool:
        """write data to a buffer prior to running ffmpeg

        :param stream: input stream id, index to self._input_info
        :param data: data blob if raw media data or bytes if encoded data
        :returns: the first data blob of the raw stream or all received bytes of
                  encoded stream (repeats every time) or None if no new raw
                  stream was buffered

        If ffprobe analysis is necessary to configure the FFmpeg arguments,
        every input pipe must be filled with the first batch of data. This
        function is to be called from a write function to sets pre-run written
        data aside.

        if it contains data for a new stream, attempts to configure ffmpeg args
        """

        if self._raw_pipe_buffer is None:  # encoded input

            buf = self._enc_pipe_buffer[stream]
            if buf is None:  # first write
                buf = data
            else:
                buf += data
            self._enc_pipe_buffer[stream] = buf

            # replace the keyword's pipe url with the data
            urls = self["input_urls"]
            urls[stream] = (buf, urls[stream][1])

        else:  # raw or encoded input
            if isinstance(data, bytes):
                stream = stream - self._nraw
                assert stream >= 0
                buf = self._enc_pipe_buffer[stream]
                if buf is None:  # first write
                    buf = data
                else:
                    buf += data
                self._enc_pipe_buffer[stream] = buf

                urls = self["extra_inputs"]
                urls[stream] = (buf, urls[stream][1])
            else:
                if self._raw_pipe_buffer[stream] is None:  # first write
                    self._raw_pipe_buffer[stream] = [data]
                    kw = self["input_stream_args"]
                    kw[stream] = (data, kw[stream][1])
                else:
                    self._raw_pipe_buffer[stream].append(data)
                    return False
        return True

    def clear_keywords(self):
        # remove all the buffered data from the keywords

        if self._raw_pipe_buffer is not None:
            kw = self["input_stream_args"]
            for i, buf in enumerate(self._raw_pipe_buffer):
                if buf is not None:
                    kw[i] = (None, kw[i][1])

            kw = self["extra_inputs"]
            for i, buf in self._enc_pipe_buffer.items():
                if buf is not None:
                    kw[i] = ("-", kw[i][1])
        else:
            kw = self["input_urls"]
            for i, buf in self._enc_pipe_buffer.items():
                if buf is not None:
                    kw[i] = ("-", kw[i][1])

    def iter_raw_data(self) -> Iterator[tuple[int, RawDataBlob]]:

        if self._raw_pipe_buffer is None:
            return

        for i, buf in enumerate(self._raw_pipe_buffer):
            if buf is not None:
                for blob in buf:
                    yield i, blob

    def iter_enc_data(self) -> Iterator[tuple[int, bytes]]:

        n0 = self._nraw
        for i, buf in self._enc_pipe_buffer.items():
            if buf is not None:
                yield i + n0, buf

    def clear_data(self):

        if self._raw_pipe_buffer is not None:
            self._raw_pipe_buffer = [None] * self._nraw
        self._enc_pipe_buffer = {i: None for i in self._enc_pipe_buffer}

    @property
    def encoded_inputs_only(self) -> bool:
        return self._raw_pipe_buffer is None

    @property
    def num_encoded_inputs(self) -> int:
        return len(self._enc_pipe_buffer)

    @property
    def num_raw_inputs(self) -> int:
        return self._nraw

    @cached_property
    def input_pipes(self) -> list[int]:

        raw_streams = range(self._nraw)
        n0 = self._nraw
        enc_streams = [i + n0 for i in self._enc_pipe_buffer]
        return [*raw_streams, *enc_streams]


class BaseFFmpegRunner(metaclass=ABCMeta):
    """Base class to run FFmpeg and manage its multiple I/O's"""

    Status = FFmpegStatus

    _pipe_kws: dict

    # configure.init_media_xxx function & its keyword arguments
    _init_func: Callable
    _init_kws: InitMediaKeywordsWithInputBuffer

    # object status enum
    _status: Status = Status.NOTHING_SET

    # pre-analysis/buffering variables
    _nb_inputs: tuple[int, int] = (0, 0)  # (raw, raw+encoded)

    # ffmpeg arguments and associated input/output information
    _args: dict[str, Any]
    _input_info: list[InputInfoDict]
    _output_info: list[OutputInfoDict]
    _primary_output: int | str | None = None
    _use_std_pipes: bool = False

    # ffmpeg subprocess and associated objects
    _proc: ffmpegprocess.Popen | None = None
    _input_pipes: dict[int, InputPipeInfoDict]
    _output_pipes: dict[int, OutputPipeInfoDict]
    _stack: ExitStack
    _logger: LoggerThread

    def __init__(
        self,
        init_func: Callable,
        init_kws: dict,
        primary_output: int | str | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Base FFmpeg runner

        :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        self._init_func = staticmethod(init_func)
        self._init_kws = InitMediaKeywordsWithInputBuffer(init_kws)
        self._primary_output = primary_output

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

        self._pipe_kws = {}

    def _try_config_ffmpeg(
        self, stream: int = -1, data: bytes | RawDataBlob | None = None
    ) -> bool:
        """Configure FFmpeg options and populate stream information

        :param stream: optional new stream written since last try
        :param data: optional newly written stream data
        :return: ``True`` if FFmpeg arguments are successfully configured
                 and `_input_info` and `_output_info` lists are fully
                 populated. Excludes the pipe information.


        If this function returns ``True``, the class object is ready to call
        `_run_ffmpeg() and input and output stream information (``_input_info``
        and ``_output_info``) are successfully lists are fully populated, except
        for the pipe assignments.

        """

        if self._status > self._status.BUFFERING:
            raise FFmpegioError("FFmpeg options have already been configured.")

        kws = self._init_kws

        if stream >= 0 and data is not None:
            # load the new data blob/bytes to the respective keyword argument
            if not kws.put_data(stream, data):
                return False  # no useful new data given (i.e., data was a second
                # or later raw data blob)

        try:
            ffmpeg_args, input_info, output_info = self._init_func(**kws)
        except FFmpegioInsufficientInputData:
            # fail only if the error was caused by insufficient input data
            return False

        # Clear buffered data from the keywords dict
        kws.clear_keywords()

        # Clear buffered data from input_info
        for st in kws.input_pipes:
            info = input_info[st]
            info.pop("buffer", None)

        # save the final arguments and info lists
        self._args["ffmpeg_args"] = ffmpeg_args
        self._input_info = input_info
        self._output_info = output_info

        # ready to run
        self._status = self._status.ARGUMENTS_SET

        return True

    def _on_exit(self, rc):
        if self._status.RUNNING:
            self._stack.close()
            self._status = self._status.STOPPED

    def _run_ffmpeg(self):

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
                args, self._input_info, self._use_std_pipes
            )

        if len(self._output_info):
            output_pipes, sp_kwargs = configure.assign_output_pipes(
                args, self._output_info, self._use_std_pipes
            )
            more_args.update(sp_kwargs)

        # find the primary output stream's rate
        configure.init_named_pipes(
            input_pipes,
            output_pipes,
            self._input_info,
            self._output_info,
            update_rate=self.primary_output_rate,
            **self._pipe_kws,
        )

        self._input_pipes = input_pipes
        self._output_pipes = output_pipes
        self._args.update(more_args)
        self._status = self._status.PIPES_SET

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

        # if stdin/stdout is used, attach StdWriter/StdReader object to each
        configure.init_std_pipes(self._input_pipes, self._output_pipes, self._proc)

        # write pre-buffered data
        for st, data in self._init_kws.iter_raw_data():
            self._write_raw(st, data)
        for st, data in self._init_kws.iter_enc_data():
            self._write_encoded(st, data)

        # clear pre-buffered data
        self._init_kws.clear_data()

    def _write_encoded(self, index: int, data: bytes):
        """backend mixin for raw media writer and filter"""

        try:
            info = self._input_pipes[index]
            assert "media_type" not in self._input_info[index]
            info["writer"].write(data)
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{index} is not an encoded stream.") from e

    def _write_raw(self, index: int, data: RawDataBlob):
        """write a raw media data to a specified stream (backend)"""

        try:
            info = self._input_info[index]
            assert "media_type" in self._input_info[index]
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{index} is not a raw stream.") from e

        b = info["data2bytes"](obj=data)
        if not len(b):
            return

        self._input_pipes[index]["writer"].write(data)

    def _read_encoded(self, index: int, n: int) -> bytes:
        """read selected output stream (shared backend)"""

        try:
            info = self._output_pipes[index]
            assert "media_type" not in self._output_info[index]
            return info["reader"].read(n)
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Output Stream #{index} is not an encoded stream.") from e

    def _read_raw(self, index: int, n: int) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        try:
            info = self._output_info[index]
            assert "media_type" in self._output_info[index]
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{index} is not a raw stream.") from e

        (dtype, shape, _) = info["raw_info"]
        b = self._output_pipes[index]["reader"].read(n)

        data = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )

        # update the frame/sample counter
        # n = counter(obj=data)  # actual number read
        # self._n0[stream_id] += n

        return data

    def _terminate(self):
        """Kill FFmpeg process and close the streams"""

        if self._proc is not None and self._proc.poll() is None:
            # kill the ffmpeg runtime
            self._proc.terminate()
            if self._proc.poll() is None:
                self._proc.kill()

            self._logger.join()

    def open(self):
        """start FFmpeg processing

        Note
        ----

        It may flag to defer starting the FFmpeg process if the input streams
        are not fully specified and must wait to deduce them from the written
        data.

        """

        if self._status != self._status.NOTHING_SET:
            raise FFmpegioError("Already opened once.")

        # try configure FFmpeg arguments without any pre-buffered data
        ok = self._try_config_ffmpeg()

        # if failed to configure, need to buffer input data first
        if ok:
            # ready to roll
            self._run_ffmpeg()
        else:
            # need input data to start ffmpeg
            self._status = self._status.BUFFERING

    def close(self):
        """Kill FFmpeg process and close the streams"""

        if self._status != self._status.RUNNING:
            raise FFmpegioError("FFmpeg is not running.")

        self._terminate()

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
        """flushes and close all input pipes and waits for FFmpeg to exit

        :param timeout: a timeout for blocking in seconds, or fractions
                        thereof, defaults to None, to wait indefinitely
        :raise `TimeoutExpired`: if a timeout is set, and the process does not
                                 terminate after timeout seconds. It is safe to
                                 catch this exception and retry the wait.
        :return returncode: return subprocess Popen returncode attribute
        """

        if self._proc:

            # write the sentinel to each input queue
            for pinfo in self._input_pipes.values():
                pinfo["writer"].write(None)

            # wait until the FFmpeg finishes the job
            self._proc.wait(timeout)

            rc = self._proc.returncode
            if rc is not None:
                self._proc = None
        else:
            rc = None
        return rc

    @property
    def _args_ready(self):
        return self._status < self._status.ARGUMENTS_SET

    ##########################################################
    ### INPUT PROPERTIES
    ##########################################################

    @property
    def input_types(self) -> dict[int, MediaType | Literal["encoded"]]:
        """input pipe types (lists both encoded and raw media pipes)

        - only piped inputs are returned
        - integer keys is the unique input index (this index is not contiguous
          if non-piped inputs are also used.)
        - values are either 'video' or 'audio' if raw media stream or 'encoded'
          if encoded byte stream

        """

        kws = self._init_kws

        intypes = {
            i: "encoded"
            for i in range(
                kws.num_raw_inputs, kws.num_raw_inputs + kws.num_encoded_inputs
            )
        }

        if not kws.encoded_inputs_only:

            intypes = {
                i: {"a": "audio", "v": "video"}[av]
                for i, av in enumerate(kws["input_stream_types"])
            } | intypes

        return intypes

    ##########################################################
    ### OUTPUT PROPERTIES
    ##########################################################

    @cached_property
    def _all_output_streams_defined(self) -> bool:
        """check and remember if user provided concrete raw output streams

        :return: True if `output_streams` is not defined in init_kws
                      OR every elements of `output_streams` defines `map` option
                         AND the option values all points to a unique stream

        The outcome informs whether output properties can be evaluated solely
        from init_kws
        """

        # not yet configured, deducible only if only encoded outputs or well-defined input arguments
        kws = self._init_kws

        if "output_streams" in kws:  # raw output streams (+extra encoded)
            kw = kws["output_streams"]
            if kw is None:
                # output streams are entirely to be autodetected
                return False

            for _, opts in (
                kw if isinstance(kw, list) else iter(v[1] for v in kw.values())
            ):
                mapopts = stream_spec.parse_map_option(
                    opts["map"], input_file_id=0, parse_stream=True
                )
                if "linklabel" not in mapopts:
                    # output media type
                    media_type = stream_spec.is_unique_stream(
                        mapopts["stream_specifier"]
                    )
                    if media_type is False:
                        return False

        return True

    @cached_property
    def _piped_output_stream_indices(self) -> list[int]:

        if self._status < self._status.ARGUMENTS_SET:
            if not self._all_output_streams_defined:
                raise FFmpegioError(
                    "Should not call this function before FFmpeg arguments are ready."
                )

            # not yet configured but all piped streams are concretely identifiable

            kws = self._init_kws

            if "output_streams" in kws:  # raw output streams (+extra encoded)
                kw = kws["output_streams"]
                assert kw is not None
                streams = list(range(len(kws["output_streams"])))

                if "extra_outputs" in kws:
                    nout = len(streams)
                    streams.extend(
                        [
                            nout + i
                            for i, (url, _) in enumerate(kws["extra_outputs"])
                            if utils.is_pipe(url)
                        ]
                    )
            else:  # encoded output streams
                streams = [
                    i
                    for i, (url, _) in enumerate(kws["output_urls"])
                    if utils.is_pipe(url)
                ]

        else:
            # FFmpeg already configured
            streams = [
                i
                for i, info in enumerate(self._output_info)
                if info["dst_type"] == "buffer" and "buffer" not in info
            ]

        return streams

    def _iter_piped_output_info(self) -> Iterator[tuple[int, OutputInfoDict]]:
        assert self._status >= self._status.ARGUMENTS_SET
        for i in self._piped_output_stream_indices:
            yield i, self._output_info[i]

    @property
    def output_types(self) -> dict[int, MediaType | Literal["encoded"] | None] | None:
        """output piped types (lists both encoded and raw media pipes)

        - None if output streams are not yet concretely known
        - only piped streams are returned
        - integer keys are unique input indices (their continuity is not guaranteed
          if non-piped inputs are also used.)
        - values are either 'video' or 'audio' if raw media stream or 'encoded'
          if encoded byte stream

        """

        if self._status < self._status.ARGUMENTS_SET:

            if not self._all_output_streams_defined:
                return None

            # not yet configured, deducible only if only encoded outputs or well-defined input arguments
            kws = self._init_kws

            if "output_streams" in kws:  # raw output streams (+extra encoded)
                kw = kws["output_streams"]

                outtypes = {}
                for i, (_, opts) in enumerate(
                    kw if isinstance(kw, list) else iter(v[1] for v in kw.values())
                ):
                    mapopts = stream_spec.parse_map_option(
                        opts["map"], input_file_id=0, parse_stream=True
                    )
                    if "linklabel" in mapopts:
                        outtypes[i] = None  # linklabel requires filtergraph analysis

                    else:  # if "stream_specifier" not in mapopts:
                        media_type = stream_spec.is_unique_stream(
                            mapopts["stream_specifier"]
                        )
                        outtypes[i] = None if media_type is False else media_type

                if "extra_outputs" in kws:  # encoded output also specified
                    nout = len(kw)
                    for i, (url, _) in enumerate(kws["extra_outputs"]):
                        if utils.is_pipe(url):
                            outtypes[i + nout] = "encoded"

                return outtypes
            else:
                return {
                    i: "encoded"
                    for i, (url, _) in enumerate(kws["output_urls"])
                    if utils.is_pipe(url)
                }

        else:
            return {
                i: info.get("media_type", "encoded")
                for i, info in enumerate(self._output_info)
                if info["dst_type"] == "buffer"
            }

    @property
    def output_labels(self) -> dict[int, str | None] | None:
        """FFmpeg/custom labels of output streams

        before loading: look for map

        """

        if self._status < self._status.ARGUMENTS_SET:
            if not self._all_output_streams_defined:
                return None

            # not yet configured, deducible only if only encoded outputs or well-defined input arguments
            kws = self._init_kws

            if "output_streams" in kws:  # raw output streams (+extra encoded)
                kw = kws["output_streams"]

                outlabels = {}

                for i, (user_map, opts) in enumerate(
                    ((None, v) for v in kw)
                    if isinstance(kw, list)
                    else iter(v[1] for k, v in kw.items())
                ):
                    if user_map is not None:
                        outlabels[i] in user_map
                    else:
                        outlabels[i] = opts["map"]

                if "extra_outputs" in kws:  # encoded output also specified
                    nout = len(kw)
                    for i, (url, _) in enumerate(kws["extra_outputs"]):
                        if utils.is_pipe(url):
                            outlabels[i + nout] = f"e:{i}"

                return outlabels
            else:

                return {
                    i: f"e:{i}"
                    for i in self._piped_output_stream_indices
                    if utils.is_pipe(url)
                }

        else:
            return {
                i: v.get("user_map", None) if "user_map" in v else f"e:{i}"
                for i, v in self._iter_piped_output_info()
            }


class PipedFFmpegRunner(BaseFFmpegRunner):
    """Base class to run FFmpeg with pipes and manage its multiple I/O's"""

    # pre-analysis/buffering variables
    _piped_inputs: dict[int, Literal["input_urls", "input_stream_args", "extra_inputs"]]
    _piped_inputs_buffer: dict[int, bytes | list[RawDataBlob]]
    # _piped_outputs_type: dict[int, MediaType | Literal["encoded"]] | None = None

    def __init__(
        self,
        init_func: Callable,
        init_kws: dict,
        primary_output: int | str | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        blocksize: int | None = None,
        queue_size: int | None = None,
        timeout: float | None = None,
    ):
        """Base FFmpeg runner

        :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        super().__init__(
            init_func,
            init_kws,
            primary_output,
            progress,
            show_log,
            overwrite,
            sp_kwargs,
            blocksize,
            queue_size,
            timeout,
        )

        # set the default read block size for the reference stream
        self._pipe_kws = {"stack": self._stack}
        if timeout is not None:
            self._pipe_kws["timeout"] = timeout
        if blocksize is not None:
            self._pipe_kws["blocksize"] = blocksize
        if queue_size is not None:
            self._pipe_kws["queue_size"] = queue_size

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
            if "extra_inputs" in kws:
                # encoded:list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
                for i, (url, _) in enumerate(kws["extra_inputs"]):
                    if utils.is_pipe(url):
                        pipes[i + n_in] = "extra_inputs"
            self._nb_inputs = (n_in, n_in + len(kws["extra_inputs"]))

    def _put_aside_input(self, stream: int, data: RawDataBlob | bytes) -> (
        tuple[
            Literal["input_urls", "input_stream_args", "extra_inputs"],
            bytes | RawDataBlob,
        ]
        | None
    ):
        """write data to a buffer prior to running ffmpeg

        :param stream: input stream id, index to self._input_info
        :param data: data blob if raw media data or bytes if encoded data
        :returns: the first data blob of the raw stream or all received bytes of
                  encoded stream (repeats every time) or None if no new raw
                  stream was buffered

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
                return self._piped_inputs[stream], buf

            else:
                assert not isinstance(buf, bytes)
                self._piped_inputs_buffer[stream].append(data)

        else:  # first write -> update the kws
            self._piped_inputs_buffer[stream] = (
                data if isinstance(data, bytes) else [data]
            )
            return self._piped_inputs[stream], data

        return None

    def _iter_input_buffer(
        self,
    ) -> Iterator[
        tuple[int, Literal["input_urls", "input_stream_args", "extra_inputs"]]
    ]:

        for itm in self._piped_inputs.items():
            yield itm

    def _write_from_buffer(self):

        for st, kw in self._piped_inputs.items():
            i = st - self._nb_inputs[0] if kw == "extra_inputs" else st

            # remove the data from the init keyword args
            self._init_kws[kw][i] = ("-", self._init_kws[kw][i][1])

            # write all the buffered data to the stream
            buf = self._piped_inputs_buffer[st]
            if isinstance(buf, bytes):  # bytes -> encoded stream
                self._input_pipes[i]["writer"].write(buf)
            else:  # raw data blob -> raw data stream
                for frame in buf:
                    self._input_pipes[i]["writer"].write(frame)

            del self._piped_inputs_buffer[buf]
