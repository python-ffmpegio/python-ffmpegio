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
    ShapeTuple,
    DTypeString,
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

    def iter_encoded_input_pipes(self) -> Iterator[int]:

        n0 = self._nraw
        return (i + n0 for i in self._enc_pipe_buffer)

    @cached_property
    def input_pipes(self) -> list[int]:

        return [*range(self._nraw), *self.iter_encoded_input_pipes()]


class BaseFFmpegRunner(metaclass=ABCMeta):
    """Base class to run FFmpeg and manage its multiple I/O's"""

    Status = FFmpegStatus

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

    _dynamic_output: bool = False
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

    @property
    def _output_rate(self) -> int | Fraction | None:
        return None

    def _run_ffmpeg(self):
        """configure pipes and run ffmpeg

        ``BaseFFmpegRunner`` neither configure/start pipes nor dump the pre-buffer
        in ``_init_kws``.
        """

        if self._status != self._status.ARGUMENTS_SET:
            if self._status < self._status.ARGUMENTS_SET:
                raise FFmpegioError(
                    "FFmpeg configuration not set. Run `config_ffmpeg()` first."
                )
            raise FFmpegioError("FFmpeg pipes have already configured.")

        # set up and activate standard pipes and read/write threads
        # configure named pipes

        self._input_pipes, self._output_pipes, more_args = self._configure_pipes()
        self._args.update(more_args)

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

        # # if stdin/stdout is used, attach StdWriter/StdReader object to each
        # configure.init_std_pipes(self._input_pipes, self._output_pipes, self._proc)

        # # write pre-buffered data
        # for st, data in self._init_kws.iter_raw_data():
        #     self._write_raw(st, data)
        # for st, data in self._init_kws.iter_enc_data():
        #     self._write_encoded(st, data)

        # # clear pre-buffered data
        # self._init_kws.clear_data()

    def _configure_pipes(
        self,
    ) -> tuple[dict[int, InputPipeInfoDict], dict[int, OutputPipeInfoDict], dict]:
        """configure pipes (both std and named)

        :return input_pipes: input pipes and their writer thread, keyed by input
                             index (i.e., index for the ``_input_info`` list)
        :return output_pipes: output pipes and their reader thread, keyed by output
                             index (i.e., index for the ``_output_info`` list)
        :return more_fp_kwargs: additional keyword arguments for ``Popen`` call
                                ``_run_ffmpeg()`` to configure std pipes

        The base implementation here only configures the pipes, opening named pipes.

        To use named pipes, this method must be extended to call
        ``configure.init_named_pipes()`` at the end.

        """

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

        return input_pipes, output_pipes, more_args

    def _write_prebuffer_to_pipes(self):
        """write pre-buffered data to FFmpeg pipes

        By default this function does nothing (suitable for readers)
        a derived writer class should reimplement this function to write
        data buffered in self._init_kws.
        """
        pass

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
    def _args_not_ready(self):
        return self._status < self._status.ARGUMENTS_SET

    ##########################################################
    ### RAW MEDIA INPUT STREAM PROPERTIES/METHODS
    ##########################################################

    @property
    def writable(self) -> bool:
        """Return ``True`` if there is at least one raw media stream to write to.
        If ``False``, ``write()`` will raise ``FFmpegioError``.

        See also: ``BaseFFmpegRunner.num_input_streams``
        """

        return self.num_input_streams > 0

    @cached_property
    def num_input_streams(self) -> int:
        """Return the number of raw media input streams.
        If ``0``, ``write()`` will raise ``FFmpegioError``."""

        try:
            return len(self._init_kws["input_stream_types"])
        except KeyError:
            return 0

    def write(self, data: RawDataBlob, stream: int = 0):
        """write a raw media data blob to the specified stream

        :param data: raw media data blob, which is supported by one of loaded
                     plugins (e.g., a NumPy array if numpy is importable in the
                     Python workspace). The shape and dtype of the data must be
                     compatible with the stream's shape and pix_fmt/sample_fmt.
        :param stream: stream index in accordance to the ``input_stream_types``
                       input array, defaults to 0 (write to the first stream).

        """

        try:
            data2bytes = self._input_info[stream]["data2bytes"]
        except AttributeError:
            # _input_info wouldn't exist if FFmpeg is not running, write to prebuffer
            self._init_kws.put_data(stream, data)
        except KeyError as e:
            raise FFmpegioError(f"Specified {stream=} is not a raw stream.") from e
        else:
            b = data2bytes(obj=data)
            if len(b):
                self._input_pipes[stream].write(b)

    @property
    def input_types(self) -> list[MediaType]:
        """media types (list of 'audio' or 'video') of raw input pipes"""

        lut: dict[Literal["a", "v"], MediaType] = {"a": "audio", "v": "video"}

        try:
            return [lut[av] for av in self._init_kws["input_stream_types"]]
        except KeyError:
            return []

    @property
    def input_rates(self) -> list[int | Fraction]:
        """audio sample or video frame rates associated with the input media streams"""

        kws = self._init_kws
        try:
            stypes = kws["input_stream_types"]
            sargs = kws["input_stream_args"]
        except KeyError:
            return []  # no input streams

        lut: dict[Literal["a", "v"], Literal["ar", "r"]] = {"a": "ar", "v": "r"}
        return [args[lut[av]] for av, args in zip(stypes, sargs)]

    @property
    def input_dtypes(self) -> list[DTypeString] | None:
        """frame/sample data type associated with the input raw media streams

        ``None`` is returned if input stream exists but FFmpeg is not running yet
        and ``input_dtypes`` argument is not given or not fully populated.
        """

        nin = self.num_input_streams
        if nin == 0:
            return []

        try:
            # ffmpeg running
            return [v["raw_info"][0] for v in self._input_info[:nin]]
        except AttributeError:
            # not running yet, gather as much as we can
            dtypes = self._init_kws["input_dtypes"]
            return (
                None
                if dtypes is None
                or len(dtypes) != nin
                or any(dtype is None for dtype in dtypes)
                else dtypes
            )

    @property
    def input_shapes(self) -> dict[int, ShapeTuple] | None:
        """frame/sample shape associated with the input raw media streams

        ``None`` is returned if input stream is expected but FFmpeg is not running yet
        and ``input_shapes`` argument is not given or not fully populated.
        """

        nin = self.num_input_streams
        if nin == 0:
            return []

        try:
            # ffmpeg running
            return [v["raw_info"][1] for v in self._input_info[:nin]]
        except AttributeError:
            # not running yet, gather as much as we can
            shapes = self._init_kws["input_shapes"]
            return (
                None
                if shapes is None
                or len(shapes) != nin
                or any(shape is None for shape in shapes)
                else shapes
            )

    ##########################################################
    ### ENCODED INPUT STREAM PROPERTIES/METHODS
    ##########################################################

    @property
    def decodable(self) -> bool:
        """Return ``True`` if there is at least one encoded stream to write.
        If ``False``, ``write_encoded()`` will raise ``FFmpegioError``."""

        return self.num_encoded_input_streams > 0

    @cached_property
    def num_encoded_input_streams(self) -> int:
        """Return the number of encoded input streams.
        If ``0``, ``write_encoded()`` will raise ``FFmpegioError``."""

        return len(self.encoded_input_streams)

    @cached_property
    def encoded_input_streams(self) -> list[int]:
        """Return a list of encoded piped input streams.
        If empty, write_encoded() will raise FFmpegioError."""

        kws = self._init_kws
        url_kw_or_none = kws.get("input_urls", kws.get("extra_inputs", None))
        return (
            []
            if url_kw_or_none is None
            else [i for i, url in enumerate(kws[url_kw_or_none]) if utils.is_pipe(url)]
        )

    def write_encoded(self, data: bytes, stream: int = 0):
        """write encoded media data to the specified encoded stream

        :param data: encoded media data bytes to be written.
        :param stream: encoded input stream index, defaults to 0 (write to the
                       first stream). Note that this stream index is that of all
                       encoded inputs. For example, if the runner is set up with
                       ``input_urls = ['video.mp4','-']`` then ``stream=0`` points
                       to `'video.mp4'` thus the write would fail, and ``stream=1``
                       must be specified to write to the input pipe.

        """

        if stream not in self.encoded_input_streams:
            raise FFmpegioError(f"Specified {st=} is not a valid input encoded stream.")
        if len(data):
            return  # no data to write

        st = stream + self.num_input_streams
        try:
            self._input_pipes[st].write(data)
        except AttributeError:
            # _input_info wouldn't exist if FFmpeg is not running, write to prebuffer
            self._init_kws.put_data(st, data)

    ##########################################################
    ### OUTPUT PROPERTIES
    ##########################################################

    @cached_property
    def readable(self) -> bool:
        """Return ``True`` if there is at least one raw media stream to read from.
        If ``False``, ``read()`` will raise ``FFmpegioError``."""
        return self.num_output_streams > 0

    @cached_property
    def num_output_streams(self) -> int:
        """Return the number of raw media stream to read from. If ``0``, ``read()``
        will raise ``FFmpegioError``."""

        # assuming that ``output_stream`` keyword only =specifies unique map

        try:
            return len(self._init_kws["output_streams"])
        except KeyError:
            return 0

    def read(self, n: int, stream: int=0) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        try:
            info = self._output_info[stream]
            assert "media_type" in self._output_info[stream]
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{stream} is not a raw stream.") from e

        (dtype, shape, _) = info["raw_info"]
        b = self._output_pipes[stream]["reader"].read(
            n * info['item_size'] if n > 0 else n
        )

        data = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )

        # update the frame/sample counter
        # n = counter(obj=data)  # actual number read
        # self._n0[stream_id] += n

        return data


    def __iter__(self):
        if not self.readable:
            raise FFmpegioError('No output stream to create a frame iterator')

        return self

    def __next__(self):
        # read all streams
        F = self.read(self._read_size)
        if self._output_info[self.primary_output_index]["data_is_empty"](obj=F):
            raise StopIteration
        return F
    
    @property
    def output_types(self) -> list[MediaType] | None:
        """media types of the raw media output pipes.

        Note: If a pipe outputs a filtergraph output (or streamspec is not
        unique), ``None`` is returned prior to FFmpeg starts"""

        nout = self.num_output_streams

        if nout == 0:  # no media stream
            return []

        try:
            stream_info = self._output_info
        except AttributeError:
            kw = self._init_kws["output_streams"]
            out = [""] * nout
            for i, opts in enumerate(
                kw if isinstance(kw, list) else (v for v in kw.values())
            ):
                mapopts = stream_spec.parse_map_option(
                    opts["map"], input_file_id=0, parse_stream=True
                )
                if "linklabel" in mapopts:
                    return None  # linklabel requires filtergraph analysis

                media_type = stream_spec.is_unique_stream(mapopts["stream_specifier"])
                if media_type is False:
                    return None  # just in case
                out[i] = media_type
            return out
        else:
            return [info.get("media_type", "encoded") for info in stream_info[:nout]]

    @property
    def output_labels(self) -> list[str] | None:
        """labels of the raw media output pipes.

        If the same input stream is mapped to multiple outputs without unique
        user labels, ``None`` is returned prior to FFmpeg starts"""

        nout = self.num_output_streams

        if nout == 0:  # no media stream
            return []

        try:
            stream_info = self._output_info
        except AttributeError:
            kw = self._init_kws["output_streams"]
            out = [""] * nout
            for i, (name, opts) in enumerate(
                ((None, v) for v in kw) if isinstance(kw, list) else kw.items()
            ):
                out[i] = opts["map"] if name is None else name
            return out if len(set(out)) == nout else None
        else:
            return [v["user_map"] for v in stream_info[:nout]]

    @property
    def output_rates(self) -> list[int | Fraction] | None:
        """sample or frame rates associated with the output streams

        ``None`` is returned before FFmpeg starts unless user specify the
        rates of all output streams (i.e., resample/change frame rate).
        """

        nout = self.num_output_streams

        if nout == 0:  # no output media stream
            return []

        try:
            stream_info = self._output_info
        except AttributeError:
            # ffmpeg not configured yet, get user options
            rates = [0] * nout
            kw = self._init_kws["output_streams"]
            if isinstance(kw, dict):
                kw = kw.values()
            for i, opts in enumerate(kw):
                r = opts.get("r", opts.get("ar", None))
                if r is None:
                    return None
                rates[i] = r
            return rates
        else:
            return [v["raw_info"][2] for v in stream_info[:nout]]

    @property
    def output_dtypes(self) -> list[DTypeString] | None:
        """frame/sample data type associated with the output streams

        Each element is a Numpy-style dtype string like '|u1' for unsigned 8-bit
        integer.

        If FFmpeg process has not been started, this property returns ``None``.
        """

        nout = self.num_output_streams

        if nout == 0:  # no output media stream
            return []

        try:
            stream_info = self._output_info
        except AttributeError:
            # ffmpeg not configured yet
            return None
        else:
            return [v["raw_info"][0] for v in stream_info[:nout]]

    @property
    def output_shapes(self) -> list[ShapeTuple] | None:
        """frame/sample shape associated with the output streams

        Each element is a Numpy-style shape integer tuple of each time sample.
        For a video stream, it has 3 elements (height, width, components); for
        an audio stream, it has 1 element (channels,).

        If FFmpeg process has not been started, this property returns ``None``.
        """

        nout = self.num_output_streams

        if nout == 0:  # no output media stream
            return []

        try:
            stream_info = self._output_info
        except AttributeError:
            # ffmpeg not configured yet
            return None
        else:
            return [v["raw_info"][1] for v in stream_info[:nout]]

    @property
    def primary_output_label(self) -> str | None:
        """primary raw media stream label (None if FFmpeg not started or no output raw stream)"""

        st = self.primary_output_index
        return st and self._output_info and self._output_info[st].get("user_map")

    @property
    def primary_output_index(self) -> int | None:
        """primary raw media stream index (None if FFmpeg not started or no output raw stream)"""

        return configure.find_primary_output_index(
            self._output_info, self._primary_output
        )

    @property
    def primary_output_rate(self) -> int | Fraction | None:
        """sample/frame rate of the primary raw media stream (None if FFmpeg not started or no output raw stream)"""
        st = self.primary_output_index
        try:
            return self._output_info[st]["raw_info"][-1]
        except (AttributeError, IndexError):
            return None

    ##########################################################
    ### ENCODED INPUT STREAM PROPERTIES/METHODS
    ##########################################################

    @property
    def encodable(self) -> bool:
        """Return ``True`` if there is at least one encoded stream to read.
        If ``False``, ``read_encoded()`` will raise ``FFmpegioError``."""

        return self.num_encoded_output_streams > 0

    @cached_property
    def num_encoded_output_streams(self) -> int:
        """Return the number of encoded output streams.
        If ``0``, ``read_encoded()`` will raise ``FFmpegioError``."""

        return len(self.encoded_output_streams)

    @cached_property
    def encoded_output_streams(self) -> list[int]:
        """Return a list of encoded piped output streams.
        If empty, ``read_encoded()`` will raise ``FFmpegioError``."""

        kws = self._init_kws
        url_kw_or_none = kws.get("output_urls", kws.get("extra_outputs", None))
        return (
            []
            if url_kw_or_none is None
            else [i for i, url in enumerate(kws[url_kw_or_none]) if utils.is_pipe(url)]
        )

    def read_encoded(self, n: int, stream: int = 0) -> bytes:
        """read encoded media data from the specified encoded stream

        :param n: number of bytes to be read. If <=0 to read
        :param stream: encoded output stream index, defaults to 0 (write to the
                       first stream). Note that this stream index is that of all
                       encoded inputs. For example, if the runner is set up with
                       ``input_urls = ['video.mp4','-']`` then ``stream=0`` points
                       to `'video.mp4'` thus the write would fail, and ``stream=1``
                       must be specified to write to the input pipe.
        :returns: bytes
        """

        if stream not in self.encoded_output_streams:
            raise FFmpegioError(
                f"Specified {stream=} is not a valid output encoded stream."
            )

        st = stream + self.num_output_streams
        self._output_pipes[st].read(n)


class StdFFmpegRunner(BaseFFmpegRunner):

    _use_std_pipes: bool = True

    def __init__(
        self,
        init_func: Callable,
        init_kws: dict,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Base FFmpeg runner for reading/writing with only 1 std pipe, no piped encoded I/O

        :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        super().__init__(init_func, init_kws, progress, show_log, overwrite, sp_kwargs)

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

        ok = super()._try_config_ffmpeg(stream, data)
        if ok:
            # validate
            nin = len(self._input_pipes)
            nout = len(self._output_pipes)
            if nin + nout != 1:
                raise FFmpegioError(
                    "StdFFmpegRunner can only use either stdin or stdout"
                )

    def _run_ffmpeg(self):

        super()._run_ffmpeg()

        # if stdin/stdout is used, attach StdWriter/StdReader object to each
        configure.init_std_pipes(self._input_pipes, self._output_pipes, self._proc)

        # write pre-buffered data
        for st, data in self._init_kws.iter_raw_data():
            self.write(data, st)

        # clear pre-buffered data
        self._init_kws.clear_data()

    @property
    def _args_not_ready(self):
        return self._status < self._status.ARGUMENTS_SET


class BasePipedFFmpegRunner(BaseFFmpegRunner):
    """Base class to run FFmpeg and manage its multiple I/O's"""

    _use_std_pipes: bool = False

    _pipe_kws: dict

    def __init__(
        self,
        init_func: Callable,
        init_kws: dict,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Base FFmpeg runner for reading/writing with only 1 std pipe, no piped encoded I/O

        :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        super().__init__(init_func, init_kws, progress, show_log, overwrite, sp_kwargs)

        self._pipe_kws = {}

    def _configure_pipes(
        self,
    ) -> tuple[dict[int, InputPipeInfoDict], dict[int, OutputPipeInfoDict], dict]:

        input_pipes, output_pipes, more_args = super()._configure_pipes()

        # find the primary output stream's rate
        configure.init_named_pipes(
            input_pipes,
            output_pipes,
            self._input_info,
            self._output_info,
            update_rate=self._output_rate,
            **self._pipe_kws,
        )

        return input_pipes, output_pipes, more_args
