"""SimpleStreams Module: FFmpeg"""

from __future__ import annotations

from time import time
import logging

logger = logging.getLogger("ffmpegio")

from typing import Literal, Self
from fractions import Fraction
from .._typing import RawDataBlob

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
from ..errors import FFmpegioError

from .. import configure, ffmpegprocess as fp, plugins, utils, probe
from .. import utils, configure, plugins
from ..threading import LoggerThread

from ..utils import FFmpegInputUrlComposite, FFmpegOutputUrlComposite
from ..configure import OutputDestinationDict
from contextlib import ExitStack

import sys
from time import time
from fractions import Fraction
from math import prod

from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError

# fmt:off
__all__ = [ "SimpleVideoReader", "SimpleAudioReader", "SimpleVideoWriter",
    "SimpleAudioWriter"]
# fmt:on


class SimpleReaderBase:
    """base class for SISO media read stream classes"""

    def __init__(
        self,
        *,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict],
        blocksize: int | None = None,
        show_log: bool | None,
        progress: ProgressCallable | None,
        sp_kwargs: dict,
    ):
        """Queue-less simple media io runner

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg input option dicts with zero or one streaming pipe. (only one in input or output)
        :param output_info: FFmpeg output option dicts with zero or one any streaming pipe. (only one in input or output)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param progress: progress callback function, defaults to None
        :param sp_kwargs: dictionary with keywords passed to `subprocess.Popen()` call used to run the FFmpeg.
        """

        self._input_info = input_info
        self._output_info = output_info

        self.blocksize = blocksize  #:positive int: number of video frames or audio samples to read when used as an iterator

        self._args = {
            "ffmpeg_args": ffmpeg_args,
            "progress": progress,
            "capture_log": True,
            "sp_kwargs": {**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
        }
        # create logger without assigning the source stream
        self._logger = LoggerThread(None, show_log)
        self._proc = None
        self._stack = None

    def __enter__(self) -> Self:

        self.open()
        return self

    def open(self) -> Self:
        # get std pipe
        stdin, stdout, input = configure.assign_std_pipes(
            self._args["ffmpeg_args"], self._input_info, self._output_info
        )

        if stdin == fp.PIPE or input is not None:
            raise FFmpegioError("SimpleReader only uses stdout as a pipe.")

        # run the FFmpeg
        self._proc = fp.Popen(**self._args, stdout=stdout)

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

        return self

    def close(self):
        """Flush and close this stream. This method has no effect if the stream is already
            closed. Once the stream is closed, any read operation on the stream will raise
            a ValueError.

        As a convenience, it is allowed to call this method more than once; only the first call,
        however, will have an effect.

        """

        # no need to close cleanly

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

    @property
    def output_label(self) -> str:
        """FFmpeg label of output stream"""
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

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self.blocksize)
        if F is None:
            raise StopIteration
        return F

    def readlog(self, n: int = None):
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

    def read(self, n: int = -1) -> bytes:
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
        logger.debug(f"[reader main] reading {n} samples")
        b = self._proc.stdout.read(n * self.output_samplesize if n > 0 else n)
        logger.debug(f"[reader main] read {len(b)} bytes")
        if not len(b):
            self._proc.stdout.close()
            return None
        return b

    def readinto(self, array:RawDataBlob)->int:
        """Read bytes into a pre-allocated, writable bytes-like object array and
        return the number of bytes read. For example, b might be a bytearray.

        Like read(), multiple reads may be issued to the underlying raw stream,
        unless the latter is interactive.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        return (
            self._proc.stdout.readinto(self._memoryviewer(obj=array)) // self.samplesize
        )


class SimpleVideoReader(SimpleReaderBase):

    def __init__(
        self,
        url,
        *,
        show_log=None,
        progress=None,
        blocksize=1,
        sp_kwargs=None,
        map=None,
        **options,
    ):

        if map is None:
            map = "0:V:0"

        ffmpeg_args, input_info, input_ready, output_info, output_options = (
            configure.init_media_read(url, options)
        )

        if len(input_info) != 1 or input_info[0]["media_type"] != "video":
            raise FFmpegioError(f'no video stream found in "{url}" ({map=})')

        super().__init__(
            hook.video_bytes,
            url,
            show_log,
            progress,
            blocksize,
            sp_kwargs,
            **options,
        )

    def read(self, n: int = -1) -> RawDataBlob:
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

        hook = plugins.get_hook()
        return hook.bytes_to_video(super().read(n))


class SimpleAudioReader(SimpleReaderBase):
    readable = True
    writable = False
    multi_read = False
    multi_write = False

    def __init__(
        self,
        url,
        *,
        show_log=None,
        progress=None,
        blocksize=None,
        sp_kwargs=None,
        **options,
    ):
        hook = plugins.get_hook()
        super().__init__(
            hook.bytes_to_audio,
            hook.audio_bytes,
            url,
            show_log,
            progress,
            blocksize,
            sp_kwargs,
            **options,
        )

    def _finalize(self, ffmpeg_args):
        # finalize FFmpeg arguments and output array

        outopts = ffmpeg_args["outputs"][0][1]
        outopts["map"] = "0:a:0"
        (
            self.dtype,
            self.shape,
            self.rate,
        ) = configure.finalize_audio_read_opts(
            ffmpeg_args,
            input_info=[
                {
                    "src_type": (
                        "filtergraph" if outopts.get("f", None) == "lavfi" else "url"
                    )
                }
            ],
        )

    def _finalize_array(self, info):
        # finalize array setup from FFmpeg log

        self.rate = info["ar"]
        self.dtype, self.shape = utils.get_audio_format(
            info["sample_fmt"], info.get("ac", 1)
        )

    @property
    def channels(self):
        return self.shape[-1]


###########################################################################


class SimpleWriterBase:
    def __init__(
        self,
        viewer,
        url,
        input_shape=None,
        input_dtype=None,
        show_log=None,
        progress=None,
        overwrite=None,
        extra_inputs=None,
        sp_kwargs=None,
        **options,
    ) -> None:
        self._proc = None
        self._viewer = viewer
        self.input_dtype = input_dtype
        self.input_shape = input_shape

        # get url/file stream
        url, stdout, _ = configure.check_url(url, True)

        options = {"probesize_in": 32, **options}
        input_options = utils.pop_extra_options(options, "_in")

        ffmpeg_args = configure.empty()
        configure.add_url(ffmpeg_args, "input", "-", input_options)
        configure.add_url(ffmpeg_args, "output", url, options)

        # add extra input arguments if given
        if extra_inputs is not None:
            configure.add_urls(ffmpeg_args, "input", extra_inputs)

        # abstract method to finalize the options only if self.dtype and self.shape are given
        ready = self._finalize(ffmpeg_args)

        # create logger without assigning the source stream
        self._logger = LoggerThread(None, show_log)

        # FFmpeg Popen arguments
        self._cfg = {**sp_kwargs} if sp_kwargs else {}
        self._cfg.update(
            {
                "ffmpeg_args": ffmpeg_args,
                "progress": progress,
                "capture_log": True,
                "overwrite": overwrite,
                "stdout": stdout,
                "bufsize": 0,
            }
        )

        if ready:
            self._open()

    def _open(self, data=None):
        # if data array is given, finalize the FFmpeg configuration with it
        if data is not None:
            self._finalize_with_data(data)

        # start FFmpeg
        self._proc = fp.Popen(**self._cfg)
        self._cfg = False

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

    def close(self):
        """close the output stream"""
        if self._proc is None:
            return

        if self._proc.stdin and not self._proc.stdin.closed:
            try:
                self._proc.stdin.close()  # flushes the buffer first before closing
            except OSError as e:
                logger.error(e)
        self._proc.wait()
        if self._proc.stderr and not self._proc.stderr.closed:
            try:
                self._proc.stderr.close()
            except OSError as e:
                logger.error(e)

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

        if self._cfg:
            # if FFmpeg not yet started, finalize the configuration with
            # the data and start
            self._open(data)

        logger.debug("[writer main] writing...")

        try:
            self._proc.stdin.write(self._viewer(obj=data))
        except (BrokenPipeError, OSError):
            self._logger.join_and_raise()

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
        *,
        input_shape=None,
        input_dtype=None,
        extra_inputs=None,
        overwrite=None,
        show_log=None,
        progress=None,
        sp_kwargs=None,
        **options,
    ):
        options["r_in"] = rate_in
        if "r" not in options:
            options["r"] = rate_in

        super().__init__(
            plugins.get_hook().video_bytes,
            url,
            input_shape,
            input_dtype,
            show_log,
            progress,
            overwrite,
            extra_inputs,
            sp_kwargs,
            **options,
        )

    def _finalize(self, ffmpeg_args) -> None:
        inopts = ffmpeg_args["inputs"][0][1]
        inopts["f"] = "rawvideo"

        ready = "s" in inopts and "pix_fmt" in inopts

        if not (ready or (self.input_dtype is None or self.input_shape is None)):
            s, pix_fmt = utils.guess_video_format((self.input_shape, self.input_dtype))
            if "s" not in inopts:
                inopts["s"] = s
            if "pix_fmt" not in inopts:
                inopts["pix_fmt"] = pix_fmt
            ready = True

        if ready:
            # set basic video filter chain if related options are specified
            configure.build_basic_vf(
                ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1)
            )
        return ready

    def _finalize_with_data(self, data):
        ffmpeg_args = self._cfg["ffmpeg_args"]
        inopts = ffmpeg_args["inputs"][0][1]
        shape, dtype = plugins.get_hook().video_info(obj=data)
        s, pix_fmt = utils.guess_video_format(shape, dtype)

        configure.build_basic_vf(
            ffmpeg_args, configure.check_alpha_change(ffmpeg_args, -1)
        )

        if "s" not in inopts:
            inopts["s"] = s
        if "pix_fmt" not in inopts:
            inopts["pix_fmt"] = pix_fmt

        self.input_shape = shape
        self.input_dtype = dtype


class SimpleAudioWriter(SimpleWriterBase):
    readable = False
    writable = True
    multi_read = False
    multi_write = False

    def __init__(
        self,
        url,
        rate_in,
        *,
        input_shape=None,
        input_dtype=None,
        extra_inputs=None,
        overwrite=None,
        show_log=None,
        progress=None,
        sp_kwargs=None,
        **options,
    ):
        options["ar_in"] = rate_in
        if "ar" not in options:
            options["ar"] = rate_in

        super().__init__(
            plugins.get_hook().audio_bytes,
            url,
            input_shape,
            input_dtype,
            show_log,
            progress,
            overwrite,
            extra_inputs,
            sp_kwargs,
            **options,
        )

    def _finalize(self, ffmpeg_args):
        # ffmpeg_args must have sample format & sampling rate specified
        inopts = ffmpeg_args["inputs"][0][1]
        ready = "sample_fmt" in inopts and "ac" in inopts

        if not ready and (self.input_dtype is not None or self.input_shape is not None):
            inopts = ffmpeg_args["inputs"][0][1]
            inopts["sample_fmt"], inopts["ac"] = utils.guess_audio_format(
                self.input_shape, self.input_dtype
            )
            ready = True

        if ready and not ("c:a" in inopts or "acodec" in inopts):
            # fill audio codec and format options
            inopts["c:a"], inopts["f"] = utils.get_audio_codec(inopts["sample_fmt"])
            if "acodec" in inopts:
                del inopts["acodec"]

        return ready

    def _finalize_with_data(self, data):
        self.input_shape, self.input_dtype = plugins.get_hook().audio_info(obj=data)

        inopts = self._cfg["ffmpeg_args"]["inputs"][0][1]
        inopts["sample_fmt"], inopts["ac"] = utils.guess_audio_format(
            self.input_shape, self.input_dtype
        )
        inopts["c:a"], inopts["f"] = utils.get_audio_codec(inopts["sample_fmt"])
