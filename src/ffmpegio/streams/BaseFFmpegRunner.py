from __future__ import annotations

import logging
from abc import ABCMeta
from contextlib import ExitStack
from enum import IntEnum
from fractions import Fraction
from functools import cached_property

from .. import configure, ffmpegprocess, stream_spec, utils
from .._typing import (
    Any,
    Callable,
    DTypeString,
    FFmpegOptionDict,
    InputInfoDict,
    InputPipeInfoDict,
    Iterator,
    Literal,
    MediaType,
    OutputInfoDict,
    OutputPipeInfoDict,
    ProgressCallable,
    RawDataBlob,
    Sequence,
    ShapeTuple,
    override,
)
from ..configure import (
    FFmpegInputOptionTuple,
    FFmpegInputUrlComposite,
    FFmpegMediaKwsDict,
    FFmpegOutputOptionTuple,
    FFmpegOutputUrlComposite,
    MediaFilterKwsDict,
    MediaReadKwsDict,
    MediaTranscoderKwsDict,
    MediaWriteKwsDict,
)
from ..errors import FFmpegError, FFmpegioError, FFmpegioInsufficientInputData
from ..threading import LoggerThread

logger = logging.getLogger("ffmpegio")

__all__ = [
    "BaseFFmpegRunner",
    "StdFFmpegRunner",
    "PipedFFmpegRunner",
    "SISOFFmpegFilter",
]


class FFmpegStatus(IntEnum):
    """FFmpeg runner status enum

    FFmpeg runners are in one of the following 5 states:

    =============  =====  ======================================================
    member         value  description
    =============  =====  ======================================================
    PREOPEN          0    Runner is not opened yet
    BUFFERING        1    Runner was opened but requires buffering input to
                          complete analysis before running FFmpeg
    ANALYSIS_DONE    2    Runner has completed analyzing the input, starting
                          FFmpeg subprocess
    RUNNING          3    FFmpeg subprocess is running
    STOPPED          4    FFmpeg subprocess has stopped
    =============  =====  ======================================================


    """

    PREOPEN = 0
    BUFFERING = 1
    ANALYSIS_DONE = 2
    RUNNING = 3
    STOPPED = 4


class InitMediaKeywordsWithInputBuffer(dict):
    """class to buffer FFmpeg input data before running it to probe configuration information"""

    # pre-analysis/buffering variables
    _nraw = 0
    _raw_pipe_buffer: None | list[list[RawDataBlob] | None]  # for 'input_stream_args'
    _enc_pipe_buffer: dict[int, bytes | None]  # for 'input_urls' or 'extra_inputs'
    # end-of-stream flags: True if buffer contains the entirety of the stream
    _raw_pipe_eos: list[bool]
    _enc_pipe_eos: dict[int, bool]

    def __init__(self, init_kws: dict):
        """identify which input init_fun keyword arguments require data from pipe"""
        super().__init__(init_kws)
        self._raw_input = "input_stream_args" in self
        self._enc_pipe_buffer = {}
        self._raw_pipe_buffer = None
        self._enc_pipe_eos = {}
        self._raw_pipe_eos = []

        # analyze the keywords and replace items to be tweaked
        if self._raw_input:
            # raw: list[tuple[RawDataBlob, FFmpegOptionDict]]
            self["input_stream_args"] = [*self["input_stream_args"]]

            self._nraw = len(self["input_stream_args"])
            self._raw_pipe_buffer = [None] * self._nraw
            self._raw_pipe_eos = [False] * self._nraw

            if "extra_inputs" in self and self["extra_inputs"] is not None:
                # encoded:list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
                self["extra_inputs"] = [*self["extra_inputs"]]

                for i, (url, _) in enumerate(self["extra_inputs"]):
                    if utils.is_pipe(url):
                        self._enc_pipe_buffer[i] = b""
                        self._enc_pipe_eos[i] = False

        else:
            # encoded: list[tuple[FFmpegInputUrlComposite, FFmpegOptionDict]]
            self["input_urls"] = [*self["input_urls"]]

            for i, (url, _) in enumerate(self["input_urls"]):
                if utils.is_pipe(url):
                    self._enc_pipe_buffer[i] = None
                    self._enc_pipe_eos[i] = False

    def put_data(self, stream: int, data: RawDataBlob | bytes, last: bool) -> bool:
        """write data to a buffer prior to running ffmpeg

        :param stream: input stream id, index to self._input_info
        :param data: data blob if raw media data or bytes if encoded data
        :param last: True if data is the last blob for the stream
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
            if self._enc_pipe_eos[stream]:
                raise FFmpegioError(f"No more data can be written to the {stream=}")

            buf = self._enc_pipe_buffer[stream]
            if buf is None:  # first write
                buf = data
            else:
                buf += data
            self._enc_pipe_buffer[stream] = buf

            # replace the keyword's pipe url with the data
            urls = self["input_urls"]
            urls[stream] = (buf, urls[stream][1])

            if last:
                self._enc_pipe_eos[stream] = True

        else:  # raw or encoded input
            if isinstance(data, bytes):
                if self._enc_pipe_eos[stream]:
                    raise FFmpegioError(f"No more data can be written to the {stream=}")
                stream = stream - self._nraw
                assert stream >= 0
                buf = self._enc_pipe_buffer[stream]
                if buf is None:  # first write
                    buf = data
                else:
                    buf += data
                self._enc_pipe_buffer[stream] = buf
                if last:
                    self._enc_pipe_eos[stream] = True

                urls = self["extra_inputs"]
                urls[stream] = (buf, urls[stream][1])
            else:
                if self._raw_pipe_eos[stream]:
                    raise FFmpegioError(f"No more data can be written to the {stream=}")
                buffer = self._raw_pipe_buffer[stream]
                if buffer is None:  # first write
                    self._raw_pipe_buffer[stream] = [data]
                    kw = self["input_stream_args"]
                    kw[stream] = (data, kw[stream][1])
                else:
                    buffer.append(data)
                    return False
                if last:
                    self._raw_pipe_eos[stream] = True
        return True

    def clear_keywords(self):
        """remove all the buffered data from the keywords"""

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

    def iter_raw_data(self) -> Iterator[tuple[int, RawDataBlob, bool]]:
        """iterate over all items in the raw media pipe buffer

        :yield index: raw stream index
        :yield data: buffered data blob
        :yield last: True if data is the last blob of the stream

        If multiple blobs are buffered for a stream, iterator yields one blob at
        a time.
        """

        if self._raw_pipe_buffer is None:
            return

        for i, (buf, eos) in enumerate(zip(self._raw_pipe_buffer, self._raw_pipe_eos)):
            if buf is not None:
                for blob in buf[:-1]:
                    yield i, blob, False
                yield i, buf[-1], eos

    def iter_enc_data(self) -> Iterator[tuple[int, bytes, bool]]:
        """iterate over all items in the encoded pipe buffer

        :yield index: encoded stream index
        :yield data: buffered data
        :yield last: True if data is the entirety of the stream content
        """
        for i, buf in self._enc_pipe_buffer.items():
            if buf is not None:
                yield i, buf, self._enc_pipe_eos[i]

    def clear_data(self):
        """release all the data blobs"""
        if self._raw_pipe_buffer is not None:
            self._raw_pipe_buffer = [None] * self._nraw
        self._enc_pipe_buffer = {i: None for i in self._enc_pipe_buffer}

    @property
    def encoded_inputs_only(self) -> bool:
        """True if no raw stream"""
        return self._raw_pipe_buffer is None

    @property
    def num_encoded_inputs(self) -> int:
        """Number of encoded streams"""
        return len(self._enc_pipe_buffer)

    @property
    def num_raw_inputs(self) -> int:
        """Number of raw streams"""
        return self._nraw

    def iter_encoded_input_pipes(self) -> Iterator[int]:
        """iterates over encoded input pipes

        :yield: index of an encoded input pipe
        """
        n0 = self._nraw
        return (i + n0 for i in self._enc_pipe_buffer)

    @cached_property
    def input_pipes(self) -> list[int]:
        """list of the indices of all input pipes"""
        return [*range(self._nraw), *self.iter_encoded_input_pipes()]


class BaseFFmpegRunner(metaclass=ABCMeta):
    Status = FFmpegStatus

    _probesize: int = 32
    _dynamic_output: bool = False
    _use_std_pipes: bool = False
    _use_named_pipes: bool = False

    # object status enum
    _status: Status = Status.PREOPEN

    # configure.init_media_xxx function & its keyword arguments
    _init_func: Callable
    _init_kws: InitMediaKeywordsWithInputBuffer
    _pipe_kws: dict[str, Any]
    _primary_output: int | None = None
    _blocksize: int | None  # read/queue blocksize in primary output's

    # ffmpeg arguments and associated input/output information
    _args: dict[str, Any]
    _input_info: list[InputInfoDict]
    _output_info: list[OutputInfoDict]

    # ffmpeg subprocess and associated objects
    _proc: ffmpegprocess.Popen | None = None
    _input_pipes: dict[int, InputPipeInfoDict]
    _output_pipes: dict[int, OutputPipeInfoDict]
    _stack: ExitStack
    _logger: LoggerThread

    def __init__(
        self,
        init_func: Callable,
        init_kws: FFmpegMediaKwsDict,
        *,
        primary_output: int | None = None,
        blocksize: int | None = None,
        enc_blocksize: int | None = None,
        queuesize: int | None = None,
        timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Streaming FFmpeg runner using std pipes and/or named pipes

        :param init_func: FFmpeg initialization function from :py:module:`configure`
        :param init_kws: keyword arguments to call the FFmpeg initialization function
        :param primary_output: (only for multi-stream readable) index of a raw
                               media output stream which serves as a frame count
                               reference , defaults to ``0``.
        :param blocksize: (only for readable) iterator block size in frames/samples
                          to read raw media streams. If multiple output streams,
                          this size specifies the size for the ``primary_output``
                          stream. If named pipes are used, this size is also the
                          size of queue items of the primary stream, defaults to
                          use ``1`` for a video stream and ``1024`` for audio stream.
        :param enc_blocksize: (only for decodable with named pipes) the queue item
                              size of encoded output stream in bytes, defaults to
                              1 MB (1024**2 bytes).
        :param queuesize: the depth of named pipe queues, defaults to None (4).
                          For unlimited queue size, specify zero (0).
        :param timeout: Default queue read timeout in seconds, defaults to `None` to
                        wait indefinitely. Note this timeout does not apply to
                        stdout pipe operation.
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console,
                         defaults to None (no show/capture)
        :param overwrite: _description_, defaults to None
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        self._init_func = staticmethod(init_func)
        self._init_kws = InitMediaKeywordsWithInputBuffer(init_kws)
        self._pipe_kws = {
            "queue_size": queuesize,
            "timeout": timeout,
            "enc_blocksize": enc_blocksize,
        }
        self._primary_output = primary_output
        self._blocksize = blocksize

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

    def __bool__(self) -> bool:
        """True if prebuffering or FFmpeg is running"""

        return self._status in (FFmpegStatus.BUFFERING, FFmpegStatus.RUNNING)

    @property
    def status(self) -> FFmpegStatus:
        """current status of the object"""
        return self._status

    def _try_config_ffmpeg(
        self,
        stream: int = -1,
        data: bytes | RawDataBlob | None = None,
        last: bool = False,
    ) -> bool:
        """Configure FFmpeg options and populate stream information

        :param stream: optional new stream written since last try
        :param data: optional newly written stream data
        :param last: optional ``True`` if ``data`` is the last data blob of ``stream``
        :return: ``True`` if FFmpeg arguments are successfully configured
                 and `_input_info` and `_output_info` lists are fully
                 populated. Excludes the pipe information.


        If this function returns ``True``, the class object is ready to call
        `_run_ffmpeg() and input and output stream information (``_input_info``
        and ``_output_info``) are successfully lists are fully populated, except
        for the pipe assignments.

        """

        if self._status > FFmpegStatus.BUFFERING:
            raise FFmpegioError("FFmpeg options have already been configured.")

        kws = self._init_kws

        if stream >= 0 and data is not None:
            # load the new data blob/bytes to the respective keyword argument
            if not kws.put_data(stream, data, last):
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

        # add probesize option to the input streams if not user specified
        input_args = ffmpeg_args["inputs"]
        for st in kws.input_pipes:
            opts = input_args[st][1]
            if "probesize" not in opts:
                opts["probesize"] = self._probesize

        # ready to run
        self._status = FFmpegStatus.ANALYSIS_DONE

        return True

    def _on_exit(self, rc):
        if self._status == FFmpegStatus.RUNNING:
            logger.debug("FFmpeg process has stopped")
            self._stack.close()
            self._status = FFmpegStatus.STOPPED
            logger.debug("closed pipes and their threads")

    @property
    def _output_rate(self) -> int | Fraction | None:
        return None

    def _run_ffmpeg(self):
        """configure pipes and run ffmpeg

        ``BaseFFmpegRunner`` neither configure/start pipes nor dump the pre-buffer
        in ``_init_kws``.
        """

        if self._status != FFmpegStatus.ANALYSIS_DONE:
            if self._status < FFmpegStatus.ANALYSIS_DONE:
                raise FFmpegioError(
                    "FFmpeg configuration not set. Run `config_ffmpeg()` first."
                )
            raise FFmpegioError("FFmpeg pipes have already configured.")

        args = self._args["ffmpeg_args"]

        # set up and activate standard pipes and read/write threads
        # configure named pipes
        more_args = {}
        input_pipes = {}
        output_pipes = {}

        # configure the pipes
        if len(self._input_info):
            input_pipes, more_args = configure.assign_input_pipes(
                args, self._input_info, self._use_std_pipes
            )

        if len(self._output_info):
            output_pipes, sp_kwargs = configure.assign_output_pipes(
                args, self._output_info, self._use_std_pipes
            )
            more_args.update(sp_kwargs)

        self._args.update(more_args)

        # find the primary output stream's rate
        if self._use_named_pipes:
            configure.init_named_pipes(
                input_pipes,
                output_pipes,
                self._input_info,
                self._output_info,
                ref_stream=self.primary_output,
                ref_blocksize=self.primary_output_blocksize,
                stack=self._stack,
                **self._pipe_kws,
            )

        # run the FFmpeg
        try:
            self._status = FFmpegStatus.RUNNING
            self._proc = ffmpegprocess.Popen(**self._args, on_exit=self._on_exit)
        except:
            if self._stack is not None:
                self._stack.close()
            raise

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._stack.enter_context(self._logger)

        # # if stdin/stdout is used, attach StdWriter/StdReader object to each
        if self._use_std_pipes:
            configure.init_std_pipes(
                input_pipes, output_pipes, self._output_info, self._proc
            )

        self._input_pipes = input_pipes
        self._output_pipes = output_pipes

        # write pre-buffered data
        for st, data, last in self._init_kws.iter_raw_data():
            self.write(data, st, last=last)
        for st, data, last in self._init_kws.iter_enc_data():
            self.write_encoded(data, st, last=last)

        # clear pre-buffered data
        self._init_kws.clear_data()

    def _terminate(self):
        """Kill FFmpeg process and close the streams"""

        if self._proc is None or self._proc.poll() is not None:
            return

        writers = [pinfo["writer"] for pinfo in self._input_pipes.values()]
        readers = [pinfo["reader"] for pinfo in self._output_pipes.values()]

        # switch the readers to the cool-down (auto-flushing) mode
        for reader in readers:
            reader.cool_down()

        # write the sentinel to each input queue (if not already closed)
        for writer in writers:
            if not writer.closed():
                writer.write(None)

        # kill the ffmpeg runtime
        self._proc.terminate()
        if self._proc.poll() is None:
            self._proc.kill()

    def open(self):
        """start FFmpeg processing

        Note
        ----

        It may flag to defer starting the FFmpeg process if the input streams
        are not fully specified and must wait to deduce them from the written
        data.

        """

        if self._status != FFmpegStatus.PREOPEN:
            raise FFmpegioError("Already opened once.")

        # try configure FFmpeg arguments without any pre-buffered data
        ok = self._try_config_ffmpeg()

        # if failed to configure, need to buffer input data first
        if ok:
            # ready to roll
            self._run_ffmpeg()

        else:
            # need input data to start ffmpeg
            self._status = FFmpegStatus.BUFFERING

    def close(self):
        """Kill FFmpeg process and close the streams"""

        if self._status != FFmpegStatus.RUNNING:
            self._status = FFmpegStatus.STOPPED
        else:
            self._terminate()

    @property
    def closed(self) -> bool:
        """True if the stream is closed."""
        return self._proc is None or self._proc.poll() is not None

    def __enter__(self):
        if self._status == FFmpegStatus.PREOPEN:
            self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def lasterror(self) -> FFmpegError | None:
        """Last error FFmpeg posted"""
        if self._proc and self._proc.poll():
            return self._logger.Exception
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
        return self._status < FFmpegStatus.ANALYSIS_DONE

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

    def write(self, data: RawDataBlob, stream: int = 0, *, last: bool = False):
        """write a raw media data blob to the specified stream

        :param data: raw media data blob, which is supported by one of loaded
                     plugins (e.g., a NumPy array if numpy is importable in the
                     Python workspace). The shape and dtype of the data must be
                     compatible with the stream's shape and pix_fmt/sample_fmt.
        :param stream: stream index in accordance to the ``input_stream_types``
                       input array, defaults to 0 (write to the first stream).
        :param last: ``True`` to indicate ``data`` is the last frame of the stream.
                     Once called with ``last=True``, the input stream can no longer
                     be written.

        """

        try:
            data2bytes = self._input_info[stream]["data2bytes"]
        except AttributeError as e:
            if self._status == FFmpegStatus.BUFFERING:
                if self._try_config_ffmpeg(stream, data, last):
                    self._run_ffmpeg()
            else:
                raise FFmpegioError(
                    "unknown error occurred (_input_info missing)"
                ) from e
        except KeyError as e:
            raise FFmpegioError(f"Specified {stream=} is not a raw stream.") from e
        else:
            b = data2bytes(obj=data)
            writer = self._input_pipes[stream]["writer"]
            if len(b):
                writer.write(b)
            if last:
                writer.write(None)  # write the sentinel

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
        return [args[1][lut[av]] for av, args in zip(stypes, sargs)]

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
    def input_shapes(self) -> list[ShapeTuple] | None:
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
        """Return ``True`` if there is at least one encoded stream to write to.
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
            else [i for i, (url, _) in enumerate(url_kw_or_none) if utils.is_pipe(url)]
        )

    def write_encoded(self, data: bytes, stream: int = 0, *, last: bool = False):
        """write encoded media data to the specified encoded stream

        :param data: encoded media data bytes to be written.
        :param stream: encoded input stream index, defaults to 0 (write to the
                       first stream). Note that this stream index is that of all
                       encoded inputs. For example, if the runner is set up with
                       ``input_urls = ['video.mp4','-']`` then ``stream=0`` points
                       to `'video.mp4'` thus the write would fail, and ``stream=1``
                       must be specified to write to the input pipe.
        :param last: ``True`` to indicate ``data`` is the last frame of the stream.
                     Once called with ``last=True``, the input stream can no longer
                     be written.

        """

        if stream not in self.encoded_input_streams:
            raise FFmpegioError(f"Specified {st=} is not a valid input encoded stream.")
        if len(data) == 0:
            return  # no data to write

        st = stream + self.num_input_streams
        try:
            writer = self._input_pipes[st]["writer"]
        except AttributeError as e:
            # _input_info wouldn't exist if FFmpeg is not running, write to prebuffer
            if self._status == FFmpegStatus.BUFFERING:
                if self._try_config_ffmpeg(st, data, last):
                    self._run_ffmpeg()
            else:
                raise FFmpegioError(
                    "unknown error occurred (_input_info missing)"
                ) from e
        else:
            writer.write(data)
            if last:
                writer.write(None)

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

    def read(self, n: int, stream: int = 0) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        try:
            info = self._output_info[stream]
            assert "media_type" in self._output_info[stream]
        except AttributeError as e:
            raise FFmpegioError("FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{stream} is not a raw stream.") from e

        (dtype, shape, _) = info["raw_info"]
        b = self._output_pipes[stream]["reader"].read(n)

        data = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )

        return data

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
            return [info["media_type"] for info in stream_info[:nout]]

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
    def output_itemsizes(self) -> list[int] | None:
        """frame/sample item sizes in bytes or ``None`` if accessed before ffmpeg
        is configured.
        """

        nout = self.num_output_streams
        if nout == 0:
            return []
        try:
            stream_info = self._output_info
        except AttributeError:
            # ffmpeg not configured yet
            return None
        else:
            return [v["item_size"] for v in stream_info[:nout]]

    ### PRIMARY OUTPUT SETTING

    @property
    def primary_output(self) -> int:
        """index of the primary output stream or ``-1`` if no output raw media stream"""

        _user_val = self._primary_output
        if _user_val is None:
            return 0 if self.readable else -1
        nout = self.num_output_streams
        if _user_val < 0 or _user_val >= nout:
            raise FFmpegioError(
                f"FFmpeg runner object was created with an invalid primary stream ({_user_val})"
            )

        return _user_val

    @property
    def primary_output_blocksize(self) -> int | None:
        """blocksize for iterator-based read and if queued-stream size of block in queue"""

        if not self.readable:
            return None

        bsize = self._blocksize
        if bsize is None:
            media_types = self.output_types
            if media_types is not None:
                mtype = media_types[self.primary_output]
                bsize = {"audio": 1024, "video": 1}[mtype]

        return bsize

    @property
    def primary_output_label(self) -> str | None:
        """primary raw media stream label (None if FFmpeg not started or no output raw stream)"""

        st = self.primary_output
        if st < 0 or self._output_info is None:
            return None
        return self._output_info[st].get("user_map", None)

    @property
    def primary_output_rate(self) -> int | Fraction | None:
        """sample/frame rate of the primary raw media stream (None if FFmpeg not started or no output raw stream)"""
        st = self.primary_output
        try:
            return self._output_info[st]["raw_info"][-1]
        except (AttributeError, IndexError):
            return None

    def output_frames(
        self, primary_frames: int | None = None
    ) -> list[int | Fraction] | None:
        """calculate the number of frames of raw output streams

        :param primary_frames: number of frames of the reference output stream,
                               defaults to ``primary_output_blocksize``
        :return: numbers of frames of all the output streams. If FFmpeg process
                 has not been started, it returns None
        """
        if primary_frames is None:
            primary_frames = self.primary_output_blocksize
        rates = self.output_rates
        rate0 = self.primary_output_rate
        if primary_frames is None or rates is None or rate0 is None:
            return None

        fr = Fraction(primary_frames, rate0)
        return [r * fr for r in rates]

    def output_pending(self) -> bool:
        """True if FFmpeg is running or at least one output buffer has data"""
        return bool(self) or any(
            pipe["reader"].qsize() for pipe in self._output_pipes.values()
        )

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
            else [i for i, (url, _) in enumerate(url_kw_or_none) if utils.is_pipe(url)]
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

        try:
            pipe = self._output_pipes[st]
        except AttributeError as e:
            raise FFmpegioError("FFmpeg is not running yet.") from e

        return pipe["reader"].read(n)


class SISOMixin:
    input_rates: list[int | Fraction]
    output_rates: list[int | Fraction]
    input_dtypes: list[DTypeString] | None
    output_dtypes: list[DTypeString] | None
    input_shapes: list[ShapeTuple] | None
    output_shapes: list[ShapeTuple] | None

    @property
    def rate_in(self) -> int | Fraction | None:
        """frame/sample rate input raw stream (``None`` if no input)"""
        rates = self.input_rates
        return None if rates is None else rates[0]

    @property
    def rate(self) -> int | Fraction | None:
        """frame/sample rate output raw stream (``None`` if no output)"""
        rates = self.output_rates
        return None if rates is None else rates[0]

    @property
    def dtype_in(self) -> DTypeString | None:
        """NumPy-style data type string of the input raw stream (``None`` if no input)"""
        dtypes = self.input_dtypes
        return None if dtypes is None else dtypes[0]

    @property
    def dtype(self) -> DTypeString | None:
        """NumPy-style data type string of the output raw stream (``None`` if no output)"""
        dtypes = self.output_dtypes
        return None if dtypes is None else dtypes[0]

    @property
    def shape_in(self) -> ShapeTuple | None:
        """shape tuple of input data frame (``None`` if no input)

        - audio frame: ``(channels,)``
        - video frame: ``(height, width, components)``
        """
        shapes = self.input_shapes
        return None if shapes is None else shapes[0]

    @property
    def shape(self) -> ShapeTuple | None:
        """shape tuple of output data frame (``None`` if no output)

        - audio frame: ``(channels,)``
        - video frame: ``(height, width, components)``
        """
        shapes = self.output_shapes
        return None if shapes is None else shapes[0]


class StdFFmpegRunner(SISOMixin, BaseFFmpegRunner):
    _dynamic_output: bool = False
    _use_std_pipes: bool = True
    _use_named_pipes: bool = False

    def __init__(
        self,
        init_func: Callable,
        init_kws: MediaReadKwsDict | MediaWriteKwsDict,
        blocksize: int | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """FFmpeg runner with only 1 buffered std pipe

        :param init_func: FFmpeg initialization function from :py:module:`configure`
        :param init_kws: keyword arguments to call the FFmpeg initialization function
        :param blocksize: (only for readable) iterator block size in frames/samples
                          to read raw media streams, defaults to use ``1`` (frame)
                          for a video stream and ``1024`` (samples) for audio stream.
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults
                         to None (no show/capture)
        :param overwrite: True to overwrite existing file, defaults to False to
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None

        """
        super().__init__(
            init_func,
            init_kws,
            blocksize=blocksize,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )

    def _try_config_ffmpeg(
        self,
        stream: int = -1,
        data: bytes | RawDataBlob | None = None,
        last: bool = False,
    ) -> bool:
        """Configure FFmpeg options and populate stream information

        :param stream: optional new stream written since last try
        :param data: optional newly written stream data
        :param last: optional ``True`` if ``data`` is the last data blob of ``stream``
        :return: ``True`` if FFmpeg arguments are successfully configured
                 and ``_input_info`` and ``_output_info`` lists are fully
                 populated.

        This subclass overloading adds additional validation for having only one
        pipe to guarantee a simple operation with one buffered std pipe.

        """

        ok = super()._try_config_ffmpeg(stream, data, last)
        if ok:
            # validate
            nin = self.num_input_streams
            nout = self.num_output_streams
            nein = self.num_encoded_input_streams
            neout = self.num_encoded_output_streams
            if nin + nout + nein + neout != 1:
                if max(nin, nein) > 1:
                    raise FFmpegioError(
                        "More than one input stream assigned to use stdin"
                    )
                if max(nout, neout) > 1:
                    raise FFmpegioError(
                        "More than one output stream assigned to use stdout"
                    )
                else:
                    raise FFmpegioError(
                        "StdFFmpegRunner can only use either stdin or stdout"
                    )

        return ok

    @override
    def __iter__(self) -> Iterator[RawDataBlob]:
        """iterator to read raw media data

        :yield: data blob containing at most ``primary_output_blocksize``
                frames/samples of the output stream.

        Note: The iterator of :py:class:`streams.StdFFmpegRunner` is not compatible with
        :py:class:`streams.BaseFFmpegRunner` and :py:class:`streams.PipedFFmpegRunner`.
        The other classes yield a list of data blobs as they allow multiple output
        raw output streams.
        """

        nout = self.num_output_streams
        if nout == 0:
            raise FFmpegioError("No output stream to create a frame iterator")

        if self.decodable or self.encodable or self.writable:
            raise FFmpegioError("Frame iterator is only supported for a pure reader")

        ref_st = self.primary_output
        ref_sz = self.primary_output_blocksize

        isempty = self._output_info[ref_st]["data_is_empty"]

        F = self.read(ref_sz, ref_st)
        while not isempty(obj=F):
            yield F
            F = self.read(ref_sz, ref_st)

    @staticmethod
    def open_simple_reader(
        input_urls: list[FFmpegInputOptionTuple],
        output_options: FFmpegOptionDict,
        extra_outputs: (
            Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
        ) = None,
        squeeze: bool = True,
        blocksize: int | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        **options: FFmpegOptionDict,
    ) -> StdFFmpegRunner:
        """create a single-pipe media reader

        :param input_urls: list of input urls
        :param output_options: dict of FFmpeg output options. One of it items must
                                be the ``'map'`` option to uniquely specify a stream.
        :param extra_outputs: extra encoded output urls, Each element is a tuple
                                pair of url and output option dict. The url must be
                                a url and not pipes or pipe objects.
        :param squeeze: ``True`` (default) to eliminate raw output's singleton
                        dimensions. Use ``False`` to always return 2D array for
                        audio and 4D array for video.
        :param options: optional ffmpeg option dict including input, output, and
                        global options. For input options, append '_in' to the
                        end of ffmpeg option names.
        :param blocksize: read block size (in frames for video or samples
                            in audio) when the reader object is used as an iterator
        :param progress: progress callback function, defaults to None
        :param show_log: ``True`` to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param overwrite: ``True`` to overwrite extra_outputs if they exist, defaults to ``False``
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        init_kws: MediaReadKwsDict = {
            "input_urls": input_urls,
            "output_streams": [output_options],
            "options": options,
            "extra_outputs": extra_outputs,
            "squeeze": squeeze,
        }
        runner = StdFFmpegRunner(
            init_func=configure.init_media_read,
            init_kws=init_kws,
            blocksize=blocksize,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner

    @staticmethod
    def open_simple_writer(
        input_stream_type: Literal["a", "v"],
        input_stream_options: FFmpegOptionDict,
        output_urls: (
            FFmpegOutputUrlComposite
            | list[
                FFmpegOutputUrlComposite
                | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
            ]
        ),
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        **options: FFmpegOptionDict,
    ) -> StdFFmpegRunner:
        """single-pipe media writer

        :param input_stream_type: specify raw media input type
        :param input_stream_options: ffmpeg input options for the raw media input
                                        must contain a rate option (``r`` or ``ar``).
        :param output_urls: pairs of output url and options
        :param options: optional ffmpeg option dict including input, output, and
                        global options. For input options, append ``'_in'`` to the
                        end of ffmpeg option names.
        :param input_dtype: input media data type as a numpy dtype string,
                            defaults to ``None`` to autodetect
        :param input_shape: input media shape (height x width x components) for
                            video or (channels,) for audio, defaults to ``None``
                            to autodetect
        :param extra_inputs: extra encoded input urls, Each element is a tuple
                                pair of url and input option dict. The url must be
                                a url and not pipes or pipe objects.
        :param progress: progress callback function, defaults to ``None``
        :param show_log: ``True`` to show FFmpeg log messages on the console,
                            defaults to ``None`` (no show/capture)
        :param overwrite: True to overwrite output_urls if they exist, defaults to ``False``
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

        init_kws: MediaWriteKwsDict = {
            "input_stream_types": [input_stream_type],
            "input_stream_args": [(None, input_stream_options)],
            "output_urls": output_urls,
            "extra_inputs": extra_inputs,
            "options": options,
            "input_dtypes": None if input_dtype is None else [input_dtype],
            "input_shapes": None if input_shape is None else [input_shape],
        }
        runner = StdFFmpegRunner(
            init_func=configure.init_media_write,
            init_kws=init_kws,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner


class PipedFFmpegRunner(BaseFFmpegRunner):
    """Streaming FFmpeg runner using named pipes"""

    _dynamic_output: bool = False
    _use_std_pipes: bool = False
    _use_named_pipes: bool = True

    def read_nowait(self, n: int, stream: int = 0) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        try:
            info = self._output_info[stream]
            assert "media_type" in self._output_info[stream]
        except AttributeError as e:
            raise FFmpegioError("FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{stream} is not a raw stream.") from e

        (dtype, shape, _) = info["raw_info"]
        b = self._output_pipes[stream]["reader"].read_nowait(
            n * info["item_size"] if n > 0 else n
        )

        data = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )

        return data

    def read_encoded_nowait(self, n: int, stream: int = 0) -> bytes:
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

        try:
            pipe = self._output_pipes[st]
        except AttributeError:
            return b""

        return pipe["reader"].read_nowait(n)

    def __iter__(self) -> Iterator[list[RawDataBlob]]:
        """iterator to read raw media data

        :yield: a list of raw data blobs, one for each output raw media stream,
                containing at most ``primary_output_blocksize`` frames of
                the primary stream given by ``primary_output``. The frame sizes
                of other streams are proportional to their ``output_rates`` wrt
                the primary output.
        """
        nout = self.num_output_streams
        if nout == 0:
            raise FFmpegioError("No output stream to create a frame iterator")

        if self.decodable or self.encodable or self.writable:
            raise FFmpegioError("Frame iterator is only supported for a pure reader")

        nperread = self.output_frames()
        count = [self._output_info[i]["data_count"] for i in range(nout)]
        nf = nperread.copy()
        nread = [1] * nout

        # loop while FFmpeg is running
        while self:
            # read the next block of the reference stream
            out = [
                (self.read)(round(max(ni, 0)), st) for st, ni in zip(range(nout), nf)
            ]
            nread = [counti(obj=Fi) for counti, Fi in zip(count, out)]

            # yield the last read frames
            yield out

            # calculate how many frames to read next (fractional)
            nf = [nfi - nr + nnext for nfi, nr, nnext in zip(nf, nread, nperread)]

        # if there is any secondary streams with leftover frames, do the last yield
        if self.output_pending() and any(n > 0 for n in nread):
            out = [self.read(round(max(ni, 0)), st) for st, ni in zip(range(nout), nf)]
            yield out

    @staticmethod
    def open_media_reader(
        input_urls: list[FFmpegInputOptionTuple],
        output_streams: (
            list[FFmpegOptionDict] | dict[str, FFmpegOptionDict] | None
        ) = None,
        squeeze: bool = True,
        extra_outputs: (
            list[FFmpegOutputOptionTuple] | dict[str, FFmpegOptionDict] | None
        ) = None,
        primary_output: int | None = None,
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
        output_streams = utils.expand_raw_output_streams(
            output_streams, input_urls, options
        )
        init_kws: MediaReadKwsDict = {
            "input_urls": input_urls,
            "output_streams": output_streams,
            "options": options,
            "squeeze": squeeze,
            "extra_outputs": extra_outputs,
        }
        runner = PipedFFmpegRunner(
            configure.init_media_read,
            init_kws,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner

    @staticmethod
    def open_media_writer(
        output_urls: list[FFmpegOutputOptionTuple],
        input_stream_types: list[Literal["a", "v"]],
        input_stream_args: list[tuple[RawDataBlob | None, FFmpegOptionDict]],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        extra_inputs: list[FFmpegInputOptionTuple] | None = None,
        primary_output: int | None = None,
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
        init_kws: MediaWriteKwsDict = {
            "output_urls": output_urls,
            "input_stream_types": input_stream_types,
            "input_stream_args": input_stream_args,
            "options": options,
            "input_dtypes": input_dtypes,
            "input_shapes": input_shapes,
            "extra_inputs": extra_inputs,
        }
        runner = PipedFFmpegRunner(
            configure.init_media_read,
            init_kws,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner

    @staticmethod
    def open_media_filter(
        input_stream_types: list[Literal["a", "v"]],
        input_stream_opts: list[FFmpegOptionDict],
        output_streams: list[FFmpegOptionDict] | dict[str, FFmpegOptionDict],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        squeeze: bool = True,
        extra_inputs: list[FFmpegInputOptionTuple] | None = None,
        extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
        primary_output: int | None = None,
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
        init_kws: MediaFilterKwsDict = {
            "input_stream_types": input_stream_types,
            "input_stream_args": [(None, opts) for opts in input_stream_opts],
            "output_streams": output_streams,
            "options": options,
            "extra_inputs": extra_inputs,
            "extra_outputs": extra_outputs,
            "squeeze": squeeze,
            "input_dtypes": input_dtypes,
            "input_shapes": input_shapes,
        }
        runner = PipedFFmpegRunner(
            configure.init_media_filter,
            init_kws,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner

    @staticmethod
    def open_media_encoder(
        input_stream_types: list[Literal["a", "v"]],
        input_stream_opts: list[FFmpegOptionDict],
        output_options: list[FFmpegOptionDict],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        extra_inputs: list[FFmpegInputOptionTuple] | None = None,
        extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
        primary_output: int | None = None,
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
        output_urls: list[FFmpegOutputOptionTuple] = [
            ("-", opts) for opts in output_options
        ]
        if extra_outputs is not None:
            output_urls.extend(extra_outputs)

        init_kws: MediaWriteKwsDict = {
            "output_urls": output_urls,
            "input_stream_types": input_stream_types,
            "input_stream_args": [(None, opts) for opts in input_stream_opts],
            "options": options,
            "input_dtypes": input_dtypes,
            "input_shapes": input_shapes,
            "extra_inputs": extra_inputs,
        }
        runner = PipedFFmpegRunner(
            configure.init_media_write,
            init_kws,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner

    @staticmethod
    def open_media_decoder(
        input_options: Sequence[FFmpegOptionDict],
        output_streams: Sequence[FFmpegOptionDict] | dict[str, FFmpegOptionDict],
        squeeze: bool = True,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        extra_outputs: Sequence[FFmpegOutputOptionTuple] | None = None,
        primary_output: int | None = None,
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
        input_urls: list[FFmpegInputOptionTuple] = [
            ("-", opts) for opts in input_options
        ]
        if extra_inputs is not None:
            input_urls.extend(extra_inputs)

        init_kws: MediaReadKwsDict = {
            "input_urls": input_urls,
            "output_streams": output_streams,
            "options": options,
            "squeeze": squeeze,
            "extra_outputs": extra_outputs,
        }
        runner = PipedFFmpegRunner(
            configure.init_media_read,
            init_kws,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner

    @staticmethod
    def open_media_transcoder(
        input_options: list[FFmpegOptionDict],
        output_options: list[FFmpegOptionDict],
        extra_inputs: list[FFmpegInputOptionTuple] | None = None,
        extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
        enc_blocksize: int | None = None,
        queuesize: int | None = None,
        timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        **options: FFmpegOptionDict,
    ) -> PipedFFmpegRunner:
        input_urls = [("pipe", opts) for opts in input_options]
        output_urls = [("pipe", opts) for opts in output_options]

        if extra_inputs is not None:
            input_urls.extend(extra_inputs)
        if extra_outputs is not None:
            output_urls.extend(extra_outputs)

        init_kws: MediaTranscoderKwsDict = {
            "input_urls": input_urls,
            "output_urls": output_urls,
            "options": options,
        }
        runner = PipedFFmpegRunner(
            configure.init_media_transcode,
            init_kws,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )
        runner.open()
        return runner


class SISOFFmpegFilter(SISOMixin, PipedFFmpegRunner):
    """Streaming FFmpeg runner for a SISO filtering using named pipes.

    This class mixes in the single input convenience properties to
    the py::class`PipedFFmpegRunner`.
    """

    @staticmethod
    def create_and_open(
        input_stream_type: Literal["a", "v"],
        input_stream_opt: FFmpegOptionDict,
        output_stream: FFmpegOptionDict | None = None,
        *,
        extra_inputs: (
            list[FFmpegInputUrlComposite | FFmpegInputOptionTuple] | None
        ) = None,
        extra_outputs: (
            list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
        ) = None,
        squeeze: bool = True,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        primary_output: int | None = None,
        blocksize: int | None = None,
        enc_blocksize: int | None = None,
        queuesize: int | None = None,
        timeout: float | None = None,
        progress: Callable[[dict[str, Any], bool], bool] | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        **options,
    ) -> SISOFFmpegFilter:
        runner = SISOFFmpegFilter(
            input_stream_type,
            input_stream_opt,
            output_stream,
            extra_inputs=extra_inputs,
            extra_outputs=extra_outputs,
            squeeze=squeeze,
            input_dtype=input_dtype,
            input_shape=input_shape,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
            **options,
        )
        runner.open()
        return runner

    def __init__(
        self,
        input_stream_type: Literal["a", "v"],
        input_stream_opt: FFmpegOptionDict,
        output_stream: FFmpegOptionDict | None = None,
        *,
        extra_inputs: (
            list[FFmpegInputUrlComposite | FFmpegInputOptionTuple] | None
        ) = None,
        extra_outputs: (
            list[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple] | None
        ) = None,
        squeeze: bool = True,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        primary_output: int | None = None,
        blocksize: int | None = None,
        enc_blocksize: int | None = None,
        queuesize: int | None = None,
        timeout: float | None = None,
        progress: Callable[[dict[str, Any], bool], bool] | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
        **options,
    ):
        init_func = configure.init_media_filter
        init_kws: MediaFilterKwsDict = {
            "input_stream_types": [input_stream_type],
            "input_stream_args": [(None, input_stream_opt)],
            "output_streams": [{}] if output_stream is None else [output_stream],
            "options": options,
            "extra_inputs": extra_inputs,
            "extra_outputs": extra_outputs,
            "squeeze": squeeze,
            "input_dtypes": None if input_dtype is None else [input_dtype],
            "input_shapes": None if input_shape is None else [input_shape],
        }
        super().__init__(
            init_func,
            init_kws,
            primary_output=primary_output,
            blocksize=blocksize,
            enc_blocksize=enc_blocksize,
            queuesize=queuesize,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs=sp_kwargs,
        )

    def _try_config_ffmpeg(
        self,
        stream: int = -1,
        data: bytes | RawDataBlob | None = None,
        last: bool = False,
    ) -> bool:
        """Configure FFmpeg options and populate stream information

        :param stream: optional new stream written since last try
        :param data: optional newly written stream data
        :param last: ``True`` if ``data`` is the last blob of ``stream``
        :return: ``True`` if FFmpeg arguments are successfully configured
                 and ``_input_info`` and ``_output_info`` lists are fully
                 populated.

        This subclass overloading adds additional validation for having only one
        pipe to guarantee a simple operation with one buffered std pipe.

        """

        ok = super()._try_config_ffmpeg(stream, data, last)
        if ok:
            # validate
            nin = self.num_input_streams
            nout = self.num_output_streams
            if nin != 1 or nout != 1:
                raise FFmpegioError(
                    "SISOFFmpegFilter takes only one each of raw input and output."
                )
            if self.num_encoded_input_streams or self.num_encoded_output_streams:
                raise FFmpegioError(
                    "SISOFFmpegFilter does not accept any encoded input or output."
                )

        return ok

    # def filter(self, data: RawDataBlob, *, last: bool = False) -> RawDataBlob:
    #     """filter a raw media data blob to the specified stream

    #     :param data: raw media data blob, which is supported by one of loaded
    #                  plugins (e.g., a NumPy array if numpy is importable in the
    #                  Python workspace). The shape and dtype of the data must be
    #                  compatible with the stream's shape and pix_fmt/sample_fmt.
    #     :param last: ``True`` to mark ``data`` the last input blob, defaults to
    #                  ``False``
    #     :returns: filter output blob.

    #     This method shall be used with caution especially if the input and output
    #     rates are not the same. It is recommended to set a timeout.
    #     """

    #     self.write(data, last=last)

    #     if self.rate_in is None or self.rate is None:
    #         raise FFmpegioError("FFmpeg is not running yet.")

    #     n = self._input_info[0]["data_count"](obj=data)
    #     nout = int((n * self.rate / self.rate_in))

    #     return self.read(nout)
