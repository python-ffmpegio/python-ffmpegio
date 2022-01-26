import logging
import numpy as np
from .. import utils, configure, ffmpegprocess, io, probe
from ..utils import log as log_utils, bytes_to_ndarray as _as_array

__all__ = [
    "SimpleVideoReader",
    "SimpleAudioReader",
    "SimpleVideoWriter",
    "SimpleAudioWriter",
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
        self._logger = log_utils.Logger(None, show_log)

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

    def _finalize_array(self, info):
        # finalize array setup from FFmpeg log

        self.framerate = info["r"]
        self.dtype, ncomp, _ = utils.get_video_format(info["pix_fmt"])
        self.shape = (*info["s"][::-1], ncomp)


class SimpleAudioReader(SimpleReaderBase):
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

        self.samplerate = info["ar"]
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
        shape=None,
        dtype=None,
        show_log=None,
        progress=None,
        overwrite=None,
        **options,
    ) -> None:

        self.dtype = dtype
        self.shape = shape and list(np.atleast_1d(shape))

        # get url/file stream
        url, stdout, _ = configure.check_url(url, True)

        input_options = utils.pop_extra_options(options, "_in")

        ffmpeg_args = configure.empty()
        configure.add_url(ffmpeg_args, "input", "-", input_options)
        configure.add_url(ffmpeg_args, "output", url, options)

        # abstract method to finalize the options only if self.dtype and self.shape are given
        ready = self._finalize(ffmpeg_args)

        # create logger without assigning the source stream
        self._logger = log_utils.Logger(None, show_log)

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
    def __init__(
        self, url, rate, shape=None, dtype=None, show_log=None, progress=None, **options
    ):
        options["r"] = rate
        super().__init__(url, shape, dtype, show_log, progress, **options)

    def _finalize(self, ffmpeg_args) -> None:
        inopts = ffmpeg_args["inputs"][0][1]
        inopts["f"] = "rawvideo"
        if self.dtype is not None or self.shape is not None:
            inopts["s"], inopts["pix_fmt"] = utils.guess_video_format(
                (self.shape, self.dtype)
            )
            return True
        return "s" in inopts and "pix_fmt" in inopts

    def _finalize_with_data(self, data):

        ffmpeg_args = self._cfg["ffmpeg_args"]
        inopts = ffmpeg_args["inputs"][0][1]
        inopts["s"], inopts["pix_fmt"] = utils.guess_video_format(data)


class SimpleAudioWriter(SimpleWriterBase):
    def __init__(
        self, url, rate, shape=None, dtype=None, show_log=None, progress=None, **options
    ):
        options["ar"] = rate
        super().__init__(url, shape, dtype, show_log, progress, **options)

    def _finalize(self, ffmpeg_args):
        if self.dtype is not None or self.shape is not None:
            inopts = ffmpeg_args["inputs"][0][1]
            codec, inopts["sample_fmt"] = utils.get_audio_format(self.dtype)
            inopts["c:a"] = codec
            inopts["f"] = codec[4:]
            inopts["ac"] = self.shape[:-1]
            return True
        return False

    def _finalize_with_data(self, data):

        inopts = self._cfg["ffmpeg_args"]["inputs"][0][1]
        codec, inopts["sample_fmt"] = utils.get_audio_format(data.dtype)
        self.shape = data.shape
        self.dtype = data.dtype
        inopts["c:a"] = codec
        inopts["f"] = codec[4:]
        inopts["ac"] = self.shape[-1]
