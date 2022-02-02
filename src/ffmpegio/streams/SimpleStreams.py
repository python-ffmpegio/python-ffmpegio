from email.policy import default
import logging
import numpy as np
from .. import utils, configure, ffmpegprocess, probe
from ..utils import bytes_to_ndarray as _as_array
from ..threading import (
    LoggerThread as _LogerThread,
    ReaderThread as _ReaderThread,
    WriterThread as _WriterThread,
)
from time import time as _time

__all__ = [
    "SimpleVideoReader",
    "SimpleAudioReader",
    "SimpleVideoWriter",
    "SimpleAudioWriter",
    "SimpleVideoFilter",
    # "SimpleAudioFilter", # FFmpeg does not support this operation
]


class SimpleReaderBase:
    """base class for SISO media read stream classes"""

    def __init__(
        self, url, show_log=None, progress=None, blocksize=None, **options
    ) -> None:

        self.dtype = None  # :numpy.dtype: output data type
        self.shape = (
            None  # :tuple of ints: dimension of each video frame or audio sample
        )
        self.itemsize = None  #:int: number of bytes of each video frame or audio sample
        self.blocksize = None  #:positive int: number of video frames or audio samples to read when used as an iterator

        # get url/file stream
        url, stdin, input = configure.check_url(url, False)

        input_options = utils.pop_extra_options(options, "_in")

        ffmpeg_args = configure.empty()
        configure.add_url(ffmpeg_args, "input", url, input_options)
        configure.add_url(ffmpeg_args, "output", "-", options)

        # abstract method to finalize the options => sets self.dtype and self.shape if known
        self._finalize(ffmpeg_args)

        # create logger without assigning the source stream
        self._logger = _LogerThread(None, show_log)

        # start FFmpeg
        self._proc = ffmpegprocess.Popen(
            ffmpeg_args,
            stdin=stdin,
            progress=progress,
            capture_log=True,
            close_stdin=True,
            close_stdout=False,
            close_stderr=False,
        )

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

        # if byte data is given, feed it
        if input is not None:
            self._proc.stdin.write(input)

        # wait until output stream log is captured if output format is unknown
        try:
            if self.dtype is None or self.shape is None:
                info = self._logger.output_stream()
                self._finalize_array(info)
            else:
                self._logger.index("Output")
        except:
            if self._proc.poll() is None:
                raise self._logger.Exception
            else:
                raise ValueError("failed retrieve output data format")

        self.itemsize = utils.get_itemsize(self.shape, self.dtype)

        self.blocksize = blocksize or max(1024 ** 2 // self.itemsize, 1)

    def close(self):
        """Flush and close this stream. This method has no effect if the stream is already
            closed. Once the stream is closed, any read operation on the stream will raise
            a ValueError.

        As a convenience, it is allowed to call this method more than once; only the first call,
        however, will have an effect.

        """
        self._proc.stdout.close()
        self._proc.stderr.close()
        try:
            self._proc.terminate()
        except:
            pass
        self._logger.join()

    @property
    def closed(self):
        """:bool: True if the stream is closed."""
        return self._proc.poll() is not None

    @property
    def lasterror(self):
        """:FFmpegError: Last error FFmpeg posted"""
        if self._proc.poll():
            return self._logger.Exception()
        else:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.read(self.blocksize)
        except:
            raise StopIteration

    def readlog(self, n=None):
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

    def read(self, n=-1):
        """Read and return numpy.ndarray with up to n frames/samples. If
        the argument is omitted, None, or negative, data is read and
        returned until EOF is reached. An empty bytes object is returned
        if the stream is already at EOF.

        If the argument is positive, and the underlying raw stream is not
        interactive, multiple raw reads may be issued to satisfy the byte
        count (unless EOF is reached first). But for interactive raw streams,
        at most one raw read will be issued, and a short result does not
        imply that EOF is imminent.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        b = self._proc.stdout.read(n * self.itemsize if n > 0 else n)
        if not len(b):
            self._proc.stdout.close()
        return _as_array(b, self.shape, self.dtype)

    def readinto(self, array):
        """Read bytes into a pre-allocated, writable bytes-like object array and
        return the number of bytes read. For example, b might be a bytearray.

        Like read(), multiple reads may be issued to the underlying raw stream,
        unless the latter is interactive.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        return self._proc.stdout.readinto(memoryview(array).cast("b")) // self.itemsize


class SimpleVideoReader(SimpleReaderBase):
    readable = True
    writable = False
    multi_read = False
    multi_write = False

    def _finalize(self, ffmpeg_args):
        # finalize FFmpeg arguments and output array

        inurl, inopts = ffmpeg_args.get("inputs", [])[0]
        outopts = ffmpeg_args.get("outputs", [])[0][1]
        has_fg = configure.has_filtergraph(ffmpeg_args, "video")

        pix_fmt = outopts.get("pix_fmt", None)
        if pix_fmt is None or (
            not has_fg
            and inurl not in ("-", "pipe:", "pipe:0")
            and not inopts.get("pix_fmt", None)
        ):
            # must assign output rgb/grayscale pixel format
            info = probe.video_streams_basic(inurl, 0)[0]
            pix_fmt_in = info["pix_fmt"]
            s_in = (info["width"], info["height"])
            r_in = info["frame_rate"]
        else:
            pix_fmt_in = s_in = r_in = None

        (
            self.dtype,
            self.shape,
            self.frame_rate,
        ) = configure.finalize_video_read_opts(ffmpeg_args, pix_fmt_in, s_in, r_in)

        # construct basic video filter if options specified
        configure.build_basic_vf(
            ffmpeg_args, utils.alpha_change(pix_fmt_in, pix_fmt, -1)
        )

    def _finalize_array(self, info):
        # finalize array setup from FFmpeg log

        self.frame_rate = info["r"]
        self.dtype, ncomp, _ = utils.get_video_format(info["pix_fmt"])
        self.shape = (*info["s"][::-1], ncomp)


class SimpleAudioReader(SimpleReaderBase):

    readable = True
    writable = False
    multi_read = False
    multi_write = False

    def _finalize(self, ffmpeg_args):
        # finalize FFmpeg arguments and output array

        inurl, inopts = ffmpeg_args.get("inputs", [])[0]
        has_fg = configure.has_filtergraph(ffmpeg_args, "video")

        sample_fmt_in = inopts.get("sample_fmt", None)
        ac_in = ar_in = None
        if not has_fg and sample_fmt_in is None:
            # use the same format as the input
            try:
                info = probe.audio_streams_basic(inurl, 0)[0]
                sample_fmt_in = info["sample_fmt"]
                ac_in = info.get("channels", None)
                ar_in = info.get("sample_rate", None)
            except:
                pass

        (
            _,
            self.dtype,
            ac,
            self.sample_rate,
        ) = configure.finalize_audio_read_opts(ffmpeg_args, sample_fmt_in, ac_in, ar_in)

        if ac is not None:
            self.shape = (ac,)

    def _finalize_array(self, info):
        # finalize array setup from FFmpeg log

        self.sample_rate = info["ar"]
        _, self.dtype = utils.get_audio_format(info["sample_fmt"])
        ac = info.get("ac", 1)
        self.shape = (ac,)

    @property
    def channels(self):
        return self.shape[-1]


###########################################################################


class SimpleWriterBase:
    def __init__(
        self,
        url,
        shape_in=None,
        dtype_in=None,
        show_log=None,
        progress=None,
        overwrite=None,
        **options,
    ) -> None:

        self.dtype_in = dtype_in
        self.shape_in = shape_in and list(np.atleast_1d(shape_in))

        # get url/file stream
        url, stdout, _ = configure.check_url(url, True)

        input_options = utils.pop_extra_options(options, "_in")

        ffmpeg_args = configure.empty()
        configure.add_url(ffmpeg_args, "input", "-", input_options)
        configure.add_url(ffmpeg_args, "output", url, options)

        # abstract method to finalize the options only if self.dtype and self.shape are given
        ready = self._finalize(ffmpeg_args)

        # create logger without assigning the source stream
        self._logger = _LogerThread(None, show_log)

        # FFmpeg Popen arguments
        self._cfg = {
            "ffmpeg_args": ffmpeg_args,
            "progress": progress,
            "capture_log": True,
            "overwrite": overwrite,
            "stdout": stdout,
            "close_stdin": True,
            "close_stdout": True,
            "close_stderr": False,
        }

        if ready:
            self._open()

    def _open(self, data=None):

        # if data array is given, finalize the FFmpeg configuration with it
        if data is not None:
            self._finalize_with_data(data)

        # start FFmpeg
        self._proc = ffmpegprocess.Popen(**self._cfg)
        self._cfg = False

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

    def close(self):
        """close the output stream"""
        try:
            self._proc.stdin.flush()
        except:
            pass
        self._proc.stdin.close()
        self._proc.wait()
        self._proc.stderr.close()
        self._logger.join()

    @property
    def closed(self):
        """:bool: True if stream is closed"""
        return self._proc.poll() is not None

    @property
    def lasterror(self):
        """:FFmpegError or None: Last caught FFmpeg error"""
        if self._proc.poll():
            return self._logger.Exception()
        else:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def readlog(self, n=None):
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

    def write(self, data):
        """Write the given numpy.ndarray object, data, and return the number
        of bytes written (always equal to the number of data frames/samples,
        since if the write fails an OSError will be raised).

        When in non-blocking mode, a BlockingIOError is raised if the data
        needed to be written to the raw stream but it couldn’t accept all
        the data without blocking.

        The caller may release or mutate data after this method returns,
        so the implementation should only access data during the method call.

        """

        data = np.asarray(data)

        if self._cfg:
            # if FFmpeg not yet started, finalize the configuration with
            # the data and start
            self._open(data)

        try:
            self._proc.stdin.write(data)
        except BrokenPipeError as e:
            # TODO check log for error in FFmpeg
            raise e

    def flush(self):
        self._proc.stdin.flush()


class SimpleVideoWriter(SimpleWriterBase):
    readable = False
    writable = True
    multi_read = False
    multi_write = False

    def __init__(
        self,
        url,
        rate_in,
        shape_in=None,
        dtype_in=None,
        show_log=None,
        progress=None,
        **options,
    ):
        options["r_in"] = rate_in
        super().__init__(url, shape_in, dtype_in, show_log, progress, **options)

    def _finalize(self, ffmpeg_args) -> None:
        inopts = ffmpeg_args["inputs"][0][1]
        inopts["f"] = "rawvideo"
        if self.dtype_in is not None or self.shape_in is not None:
            inopts["s"], inopts["pix_fmt"] = utils.guess_video_format(
                (self.shape_in, self.dtype_in)
            )
            return True

        ready = "s" in inopts and "pix_fmt" in inopts
        if ready:
            configure.build_basic_vf(
                ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1)
            )
        return

    def _finalize_with_data(self, data):

        ffmpeg_args = self._cfg["ffmpeg_args"]
        inopts = ffmpeg_args["inputs"][0][1]
        inopts["s"], inopts["pix_fmt"] = utils.guess_video_format(data)

        configure.build_basic_vf(
            ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1)
        )

        self.shape_in = data.shape
        self.dtype_in = data.dtype


class SimpleAudioWriter(SimpleWriterBase):
    readable = False
    writable = True
    multi_read = False
    multi_write = False

    def __init__(
        self,
        url,
        rate_in,
        shape_in=None,
        dtype_in=None,
        show_log=None,
        progress=None,
        **options,
    ):
        options["ar_in"] = rate_in
        super().__init__(url, shape_in, dtype_in, show_log, progress, **options)

    def _finalize(self, ffmpeg_args):
        if self.dtype_in is not None or self.shape_in is not None:
            inopts = ffmpeg_args["inputs"][0][1]
            codec, inopts["sample_fmt"] = utils.get_audio_format(self.dtype_in)
            inopts["c:a"] = codec
            inopts["f"] = codec[4:]
            inopts["ac"] = self.shape_in[:-1]
            return True
        return False

    def _finalize_with_data(self, data):

        inopts = self._cfg["ffmpeg_args"]["inputs"][0][1]
        codec, inopts["sample_fmt"] = utils.get_audio_format(data.dtype)
        self.shape_in = data.shape
        self.dtype_in = data.dtype
        inopts["c:a"] = codec
        inopts["f"] = codec[4:]
        inopts["ac"] = self.shape_in[-1]


###############################################################################


class SimpleFilterBase:
    """base class for SISO media filter stream classes

    :param rate_in: input sample rate
    :type rate_in: int, float, Fraction, str
    :param shape_in: input single-sample array shape, defaults to None
    :type shape_in: seq of ints, optional
    :param dtype_in: input numpy data type, defaults to None
    :type dtype_in: numpy.dtype, optional
    :param rate: output sample rate, defaults to None (auto-detect)
    :type rate: int, float, Fraction, str, optional
    :param shape: output single-sample array shape, defaults to None
    :type shape: seq of ints, optional
    :param dtype: output numpy data type, defaults to None
    :type dtype: numpy.dtype, optional
    :param block_size: read buffer block size in samples, defaults to None
    :type block_size: int, optional
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
        # fmt:off
        self, expr, rate_in, shape_in=None, dtype_in=None, rate=None,
        shape=None, dtype=None, block_size=None, default_timeout=None,
        progress=None, show_log=None, **options,
        # fmt:on
    ) -> None:

        #:float: default filter operation timeout in seconds
        self.default_timeout = default_timeout or 10e-3

        #:numpy.dtype: input array dtype
        self.dtype_in = dtype_in and np.dtype(dtype_in)
        #:tuple(int): input array shape
        self.shape_in = shape_in and tuple(np.atleast_1d(shape_in))
        #:numpy.dtype: output array dtype
        self.dtype = dtype and np.dtype(dtype)
        #:tuple(int): output array shape
        self.shape = shape and tuple(np.atleast_1d(shape))

        self.nin = 0  #:int: total number of input frames sent to FFmpeg
        self.nout = 0  #:int: total number of output frames frames received from FFmpeg
        # # of output frames per 1 input frame
        self._out2in = None if rate is None or rate_in is None else rate / rate_in

        # set this to false in _finalize() if guaranteed for the logger to have output stream info
        self._logger_timeout = True

        self._proc = None

        input_options = utils.pop_extra_options(options, "_in")

        ffmpeg_args = configure.empty()
        configure.add_url(ffmpeg_args, "input", "-", input_options)
        configure.add_url(ffmpeg_args, "output", "-", options)

        # abstract method to finalize the options only if self.dtype and self.shape are given
        ready_to_open = self._finalize(ffmpeg_args, expr, rate_in, rate)

        # create the stdin writer without assigning the sink stream
        self._writer = _WriterThread(None, 0)

        # create the stdout reader without assigning the source stream
        self._reader = _ReaderThread(None, None, None, block_size, 0)
        self._reader_needs_info = True

        # create logger without assigning the source stream
        self._logger = _LogerThread(None, show_log)

        # FFmpeg Popen arguments
        self._cfg = {
            "ffmpeg_args": ffmpeg_args,
            "progress": progress,
            "capture_log": True,
            "close_stdin": True,
            "close_stdout": False,
            "close_stderr": False,
        }

        # if input is fully configured, start FFmpeg now
        if ready_to_open:
            self._open()

    def _open(self, data=None):

        # if data array is given, finalize the FFmpeg configuration with it
        self._reader_needs_info = data is not None and self._finalize_with_data(data)

        # start FFmpeg
        self._proc = ffmpegprocess.Popen(**self._cfg)
        self._cfg = False

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

        # start the writer
        self._writer.stdin = self._proc.stdin
        self._writer.start()

        if not self._reader_needs_info:
            self._start_reader()

    def _start_reader(self, timeout):

        if self._reader_needs_info:
            # run after the first input block is sent to FFmpeg
            try:
                info = self._logger.output_stream(
                    timeout=timeout if self._logger_timeout else None
                )
            except TimeoutError as e:
                raise e
            except Exception as e:
                if self._proc.poll() is None:
                    raise self._logger.Exception
                else:
                    raise ValueError("failed retrieve output data format")

            self._finalize_output(info)
            self._reader_needs_info = False

        # start the FFmpeg output reader
        self._reader.stdout = self._proc.stdout
        self._reader.shape = self.shape
        self._reader.dtype = self.dtype
        self._reader.start()

    def close(self):
        """Close the stream.

        This method has no effect if the stream is already closed. Once the
        stream is closed, any read operation on the stream will raise a ThreadNotActive.

        As a convenience, it is allowed to call this method more than once; only the first call,
        however, will have an effect.
        """

        if self._proc is None:
            return

        # kill the process
        try:
            self._proc.terminate()
        except:
            pass

        self._proc.stdin.close()
        self._proc.stdout.close()
        self._proc.stderr.close()
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
            self._writer.join()
        except:
            # possibly close before opening the writer thread
            pass

    @property
    def closed(self):
        """:bool: True if the stream is closed."""
        return self._proc.poll() is not None

    @property
    def lasterror(self):
        """:FFmpegError: Last error FFmpeg posted"""
        if self._proc.poll():
            return self._logger.Exception()
        else:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def readlog(self, n=None):
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

    def filter(self, data, timeout=None):
        """Run filter operation

        :param data: input data block
        :type data: numpy.ndarray
        :param timeout: timeout for the operation in seconds, defaults to None
        :type timeout: float, optional
        :return: output data block
        :rtype: numpy.ndarray
        
        The input `data` array is expected to have the datatype specified by
        Filter class' `dtype_in` property and the array shape to match Filter
        class' `shape_in` property or with an additional dimension prepended.

        .. important::
          [audio only] For the first 2-seconds or 50000-samples, whichever
          is smaller, TimeoutError may be raised because the necessary output
          format information is not yet made available from FFmpeg. This
          exception, however, only indicate the lack of output data and
          the input data can be assumed properly enqueued to be sent to
          FFmpeg process

        .. important::
          Once the output format is resolved, this method always return
          numpy.ndarray object as output. However, the exact number of
          samples is unknown, and it could be a properly shaped empty
          array. Additional buffering may be required if the following
          process requires a fixed number of samples.

        .. important::
          Filtering operation is always timed because the buffering
          protocols used by various subsystems of FFmpeg are undeterminable
          from Python. The operation timeout is controlled by `timeout`
          argument if specified or else  by `default_timeout` property. The
          default timeout duration is 10 ms, but it could be optimized for
          each use case (`blocksize` property, I/O rate ratio, typical size of
          `data` argument, etc.).

        """

        timeout = timeout or self.default_timeout

        timeout += _time()
        data = np.asarray(data)

        if self._cfg:
            # if FFmpeg not yet started, finalize the configuration with
            # the data and start
            self._open(data)

        try:
            self._writer.write(data, timeout - _time())
        except BrokenPipeError as e:
            # TODO check log for error in FFmpeg
            raise e
        self.nin += data.shape[0]

        if self._reader_needs_info:
            # with the data written, FFmpeg should inform the output setup
            self._start_reader(timeout - _time())

        nread = int(self.nin * self._out2in) - self.nout
        y = self._reader.read(-nread, timeout - _time())
        self.nout += y.shape[0]
        return y

    def flush(self, timeout=None):
        """Close the stream input and retrieve the remaining output samples

        :param timeout: timeout duration in seconds, defaults to None
        :type timeout: float, optional
        :return: remaining output samples
        :rtype: numpy.ndarray
        """

        timeout = timeout or self.default_timeout

        # If no input, close stdin and read all remaining frames
        y = self._reader.read_all(timeout)
        self._proc.stdin.close()
        self._proc.wait()
        y = np.concatenate((y, self._reader.read_all(None)))
        self.nout += y.shape[0]
        return y


class SimpleVideoFilter(SimpleFilterBase):
    """SISO video filter stream class

    .. important::
        Number of output frames is not predetermined although it is
        generally close to the expected number of frames based on the
        number of input frames and the ratio of input and output frame
        rate

    :param rate_in: input frame rate
    :type rate_in: int, float, Fraction, str
    :param shape_in: input single-frame array shape, defaults to None
    :type shape_in: seq of ints, optional
    :param dtype_in: input numpy data type, defaults to None
    :type dtype_in: numpy.dtype, optional
    :param rate: output frame rate, defaults to None (auto-detect)
    :type rate: int, float, Fraction, str, optional
    :param shape: output single-frame array shape, defaults to None
    :type shape: seq of ints, optional
    :param dtype: output numpy data type, defaults to None
    :type dtype: numpy.dtype, optional
    :param block_size: read buffer block size in frames, defaults to None (=1)
    :type block_size: int, optional
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

    readable = True
    writable = True
    multi_read = False
    multi_write = False

    def __init__(
        # fmt:off
        self, expr, rate_in, shape_in=None, dtype_in=None, rate=None, shape=None, dtype=None,
        block_size=None, default_timeout=None, progress=None, show_log=None, **options,
        # fmt:on
    ) -> None:
        self.frame_rate_in = None
        self.frame_rate = None
        # fmt:off
        super().__init__(
            expr, rate_in, shape_in, dtype_in, rate, shape, dtype,
            block_size, default_timeout, progress, show_log, **options,
        )
        # fmt:on

    def _finalize(self, ffmpeg_args, expr, rate_in, rate) -> None:
        inopts = ffmpeg_args["inputs"][0][1]
        outopts = ffmpeg_args.get("outputs", [])[0][1]
        inopts["f"] = "rawvideo"
        outopts["f"] = "rawvideo"
        if expr:
            outopts["vf"] = expr

        inopts["r"] = self.frame_rate_in = rate_in
        self.frame_rate = rate if rate else None
        if rate is not None:
            outopts["r"] = rate

        self._out2in = self.frame_rate and self.frame_rate / self.frame_rate_in

        self._logger_timeout = False

        if self.dtype_in is None or self.shape_in is None:
            s = inopts.get("s", None)
            pix_fmt = inopts.get("pix_fmt", None)
            if s and pix_fmt:
                # if both s and pix_fmt are set, we are ready to roll
                self.dtype_in, ncomp, _ = utils.get_video_format(pix_fmt)
                s = utils.parse_video_size(s)
                self.shape_in = (s[1], s[0], ncomp)
        else:
            # if both dtype and shape specified, override input options if needed
            inopts["s"], inopts["pix_fmt"] = utils.guess_video_format(
                (self.shape_in, self.dtype_in)
            )

        if self.dtype is None or self.shape is None:
            s = outopts.get("s", None)
            pix_fmt = outopts.get("pix_fmt", None)
            if s and pix_fmt:
                self.dtype, ncomp, _ = utils.get_video_format(pix_fmt)
                s = utils.parse_video_size(s)
                self.shape = (s[1], s[0], ncomp)
        else:
            outopts["s"], outopts["pix_fmt"] = utils.guess_video_format(
                (self.shape, self.dtype)
            )

        ready = "s" in inopts and "pix_fmt" in inopts
        if ready:
            configure.build_basic_vf(
                ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1)
            )

        return ready

    def _finalize_with_data(self, data):

        ffmpeg_args = self._cfg["ffmpeg_args"]
        inopts = ffmpeg_args["inputs"][0][1]
        inopts["s"], inopts["pix_fmt"] = utils.guess_video_format(data)

        configure.build_basic_vf(
            ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1)
        )

        # if output rate, shape, & dtype not known, it needs to be analyzed from the log
        return self.frame_rate is None or self.shape is None or self.dtype is None

    def _finalize_output(self, info):
        # finalize array setup from FFmpeg log
        self.frame_rate = info["r"]
        self.dtype, ncomp, _ = utils.get_video_format(info["pix_fmt"])
        self.shape = (*info["s"][::-1], ncomp)
        self._out2in = self.frame_rate and self.frame_rate / self.frame_rate_in


class SimpleAudioFilter(SimpleFilterBase):
    """SISO audio filter stream class

    .. important::
        If the total duration of the stream is less than 2 seconds, use
        :py:func:`audio.filter` function instead. FFmpeg does not start
        the filtering process until about 2-seconds or about 50000-samples
        worth of data are first accumulated. No output data will be produced
        during this initial accumulation period.

    .. important::
        The exact number of output samples after each :py:meth:`filter`
        call is not known and can be zero.

    :param rate_in: input sample rate
    :type rate_in: int, float, Fraction, str
    :param shape_in: input single-sample array shape, defaults to None
    :type shape_in: seq of ints, optional
    :param dtype_in: input numpy data type, defaults to None
    :type dtype_in: numpy.dtype, optional
    :param rate: output sample rate, defaults to None (auto-detect)
    :type rate: int, float, Fraction, str, optional
    :param shape: output single-sample array shape, defaults to None
    :type shape: seq of ints, optional
    :param dtype: output numpy data type, defaults to None
    :type dtype: numpy.dtype, optional
    :param block_size: read buffer block size in samples, defaults to None (=>1024)
    :type block_size: int, optional
    :param default_timeout: default filter timeout in seconds, defaults to None (100 ms)
    :type default_timeout: float, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                    defaults to None (no show/capture)
    :type show_log: bool, optional
    :param \\**options: FFmpeg options, append '_in' for input option names (see :doc:`options`)
    :type \\**options: dict, optional

    ..note::
        Use of larger `block_size` parameter could improve the processing speed

    """

    readable = True
    writable = True
    multi_read = False
    multi_write = False

    def _finalize(self, ffmpeg_args, expr, rate_in, rate):

        inopts = ffmpeg_args["inputs"][0][1]
        outopts = ffmpeg_args.get("outputs", [])[0][1]
        if expr:
            outopts["af"] = expr

        #:int: input sampling rate in samples/second
        self.sample_rate_in = rate_in
        #:int: output sampling rate in samples/second
        self.sample_rate = rate if rate else None

        if rate:
            outopts["ar"] = self.sample_rate = rate
        if rate_in:
            inopts["ar"] = rate_in
        elif "ar" not in inopts:
            inopts["ar"] = rate
        self._out2in = self.sample_rate and self.sample_rate / self.sample_rate_in

        if self.dtype_in is None or self.shape_in is None:
            ac = inopts.get("ac", None)
            sample_fmt = inopts.get("sample_fmt", None)
            if ac and sample_fmt:
                codec, self.dtype_in = utils.get_audio_format(sample_fmt)
                inopts["f"] = codec[4:]
                inopts["c:a"] = codec
                self.shape_in = (ac,)
        else:
            # if both dtype and shape specified, override input options if needed
            self._set_input(self.shape_in, self.dtype_in)

        if self.dtype is not None and self.shape is not None:
            outopts["ac"], outopts["sample_fmt"] = utils.guess_audio_format(
                (self.shape, self.dtype)
            )
        elif "ac" in outopts and "sample_fmt" in outopts:
            self._finalize_output(outopts)

        return "ac" in inopts and "sample_fmt" in inopts

    def _set_input(self, shape, dtype):
        # finalize array setup from FFmpeg log

        inopts = self._cfg["ffmpeg_args"]["inputs"][0][1]
        codec, inopts["sample_fmt"] = utils.get_audio_format(dtype)
        self.shape_in = shape and tuple(shape)
        self.dtype_in = dtype and np.dtype(dtype)
        inopts["c:a"] = codec
        inopts["f"] = codec[4:]
        inopts["ac"] = self.shape_in[-1]

    def _finalize_with_data(self, data):
        # finalize array setup from FFmpeg log
        self._set_input(data.shape, data.dtype)

        # finalize the output (use input sample_fmt if not set)
        outopts = self._cfg["ffmpeg_args"]["outputs"][0][1]
        sample_fmt = outopts.get("sample_fmt", None)
        ac = outopts.get("ac", None)
        if not sample_fmt:
            inopts = self._cfg["ffmpeg_args"]["inputs"][0][1]
            sample_fmt = outopts["sample_fmt"] = inopts["sample_fmt"]
        codec, self.dtype = utils.get_audio_format(sample_fmt)
        outopts["c:a"] = codec
        outopts["f"] = codec[4:]
        if ac:
            self.shape = (ac,)

        return self.sample_rate is None or self.shape is None or self.dtype is None

    def _finalize_output(self, info):
        self.sample_rate = info["ar"]
        ac = info.get("ac", 1)
        self.shape = (ac,)
        self._out2in = self.sample_rate and self.sample_rate / self.sample_rate_in

    @property
    def channels(self):
        """:int: Number of output channels (None if not yet determined)"""
        return self.shape and self.shape[-1]

    @property
    def channels_in(self):
        """:int: Number of input channels (None if not yet determined)"""
        return self.shape_in and self.shape_in[-1]
