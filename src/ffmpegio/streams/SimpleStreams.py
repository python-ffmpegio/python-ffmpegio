"""SimpleStreams Module: FFmpeg"""

from __future__ import annotations

from time import time
import logging

logger = logging.getLogger("ffmpegio")

from ..plugins.hookspecs import FromBytesCallable, CountDataCallable, ToBytesCallable
from typing import Literal, Self
from fractions import Fraction
from .._typing import RawDataBlob

from typing_extensions import Unpack, Callable
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

from ..filtergraph.abc import FilterGraphObject
from ..errors import FFmpegioError

from .. import configure, ffmpegprocess as fp, plugins, utils, probe
from .. import utils, configure, plugins
from ..threading import LoggerThread

from ..utils import FFmpegInputUrlComposite, FFmpegOutputUrlComposite
from ..configure import OutputDestinationDict
from contextlib import ExitStack
from ..stream_spec import stream_spec_to_map_option, StreamSpecDict

import sys
from time import time
from fractions import Fraction
from math import prod

from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError

from ..configure import (
    FFmpegArgs,
    MediaType,
    InitMediaOutputsCallable,
    FFmpegUrlType,
)

from .BaseFFmpegRunner import (
    BaseFFmpegRunner,
    BaseRawInputMixin,
    BaseRawOutputMixin,
    BaseEncodedInputsMixin,
    BaseEncodedOutputsMixin,
)

# fmt:off
__all__ = [ "SimpleVideoReader", "SimpleAudioReader", "SimpleVideoWriter",
    "SimpleAudioWriter"]
# fmt:on


class RawOutputsMixin:

    default_timeout: float | None
    _input_info: list[InputSourceDict]
    _output_info: list[OutputDestinationDict]
    _deferred_data: list[list[bytes]]
    _input_ready: bool
    _logger: LoggerThread | None

    def __init__(self, blocksize, **kwargs):
        super().__init__(**kwargs)

        # set the default read block size for the reference stream
        self._blocksize = blocksize
        self._rate = None
        self._n0: int = 0  # timestamps of the last read sample


    def _read_stream_bytes(
        self,
        converter: FromBytesCallable,
        counter: CountDataCallable,
        dtype: DTypeString,
        shape: ShapeTuple,
        info: OutputDestinationDict,
        stream_id: int | str,
        n: int,
        timeout: float | None = None,
        squeeze: bool = False,
    ) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        data = converter(
            b=info["reader"].read(n, timeout), dtype=dtype, shape=shape, squeeze=squeeze
        )

        # update the frame/sample counter
        n = counter(obj=data)  # actual number read
        self._n0[stream_id] += n

        return data


class SimpleReaderBase(BaseFFmpegRunner):
    """base class for SISO media read stream classes"""

    def __init__(
        self,
        *,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict],
        from_bytes: FromBytesCallable,
        counter: CountDataCallable,
        to_memoryview: ToBytesCallable,
        show_log: bool | None,
        progress: ProgressCallable | None,
        blocksize: int,
        default_timeout: float | None,
        sp_kwargs: dict | None,
    ):
        """Queue-less simple media io runner

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg input option dicts with zero or one streaming pipe. (only one in input or output)
        :param output_info: FFmpeg output option dicts with zero or one any streaming pipe. (only one in input or output)
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        super().__init__(
            ffmpeg_args=ffmpeg_args,
            input_info=input_info,
            output_info=output_info,
            input_ready=True,
            init_deferred_outputs=None,
            deferred_output_args=[],
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            sp_kwargs={**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
            blocksize=blocksize,
            ref_output=0,
        )

        self._converter = from_bytes
        self._get_num = counter
        self._memoryviewer = to_memoryview

        # set the default read block size for the reference stream
        self._blocksize = blocksize

        # set the default read block size for the referenc stream
        info = self._output_info[0]
        assert "raw_info" in info

        self._rate = info["raw_info"][2]
        self._n0 = 0  # timestamps of the last read sample

    @property
    def output_label(self) -> str | None:
        """FFmpeg/custom labels of output streams"""
        return self._output_info[0]["user_map"]

    @property
    def output_type(self) -> MediaType | None:
        """media type associated with the output streams (key)"""
        return self._output_info[0]["media_type"]

    @property
    def output_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][2] if "raw_info" in info else None

    @property
    def output_dtype(self) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][0] if "raw_info" in info else None

    @property
    def output_shape(self) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][1] if "raw_info" in info else None

    @property
    def output_count(self) -> int:
        """number of frames/samples read"""
        return self._n0

    def _assign_pipes(self):

        configure.assign_output_pipes(
            self._args["ffmpeg_args"],
            self._output_info,
            self._args["sp_kwargs"],
            use_std_pipes=True,
        )

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize, self.default_timeout)
        if F is None:
            raise StopIteration
        return F

    def read(
        self, n: int, timeout: float | None = None, squeeze: bool = False
    ) -> RawDataBlob:
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

        info = self._output_info[0]
        converter = self._converter
        dtype, shape, _ = info["raw_info"]

        if timeout is None:
            timeout = self.default_timeout

        b = info["reader"].read(n, timeout)
        data = converter(b=b, dtype=dtype, shape=shape, squeeze=squeeze)

        # update the frame/sample counter
        n = self._get_num(
            b=b, dtype=dtype, shape=shape, squeeze=squeeze
        )  # actual number read
        self._n0 += n

        return data

    def readinto(self, array: RawDataBlob) -> int:
        """Read bytes into a pre-allocated, writable bytes-like object array and
        return the number of bytes read. For example, b might be a bytearray.

        Like read(), multiple reads may be issued to the underlying raw stream,
        unless the latter is interactive.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""
        info = self._output_info[0]
        shape = info["raw_info"][1]

        return self._proc.stdout.readinto(self._memoryviewer(obj=array)) // prod(
            shape[1:]
        )


class SimpleVideoReader(SimpleReaderBase):

    def __init__(
        self,
        url: FFmpegUrlType,
        *,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int = 1,
        sp_kwargs: dict | None = None,
        stream: str | StreamSpecDict | None = None,
        default_timeout: float | None = None,
        **options,
    ):
        # assign the input stream
        map = "0:V:0" if stream is None else stream_spec_to_map_option(stream)

        args, input_info, ready, output_info, _ = configure.init_media_read(
            [url], [map], options
        )

        if len(output_info) != 1 or output_info[0]["media_type"] != "video":
            raise FFmpegioError(f'no output video stream found in "{url}" ({map=})')

        if not all(ready):
            raise RuntimeError(
                "Given file/url does not pre-provide the media information. Use media.read instead."
            )

        hook = plugins.get_hook()

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            show_log=show_log,
            progress=progress,
            blocksize=blocksize,
            sp_kwargs=sp_kwargs,
            from_bytes=hook.bytes_to_video,
            counter=hook.video_frames,
            to_memoryview=hook.video_bytes,
            default_timeout=default_timeout,
        )


class SimpleAudioReader(SimpleReaderBase):

    def __init__(
        self,
        url: FFmpegUrlType,
        *,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int = 1,
        sp_kwargs: dict | None = None,
        stream: str | StreamSpecDict | None = None,
        default_timeout: float | None = None,
        **options,
    ):
        # assign the input stream
        map = "0:a:0" if stream is None else stream_spec_to_map_option(stream)

        args, input_info, ready, output_info, _ = configure.init_media_read(
            [url], [map], options
        )

        if len(output_info) != 1 or output_info[0]["media_type"] != "audio":
            raise FFmpegioError(f'no output audio stream found in "{url}" ({map=})')

        if not all(ready):
            raise RuntimeError(
                "Given file/url does not pre-provide the media information. Use media.read instead."
            )

        hook = plugins.get_hook()

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            show_log=show_log,
            progress=progress,
            blocksize=blocksize,
            sp_kwargs=sp_kwargs,
            from_bytes=hook.bytes_to_audio,
            counter=hook.audio_frames,
            to_memoryview=hook.audio_bytes,
            default_timeout=default_timeout,
        )


###########################################################################


class BaseRawInputsMixin:
    """write a raw media data to a specified stream (backend)"""

    default_timeout: float | None
    _input_info: list[InputSourceDict]
    _output_info: list[OutputDestinationDict]
    _deferred_data: list[list[bytes]]
    _input_ready: Literal[True] | list[bool]
    _logger: LoggerThread | None
    _open: Callable[[bool], None]
    _args: dict

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # input data must be initially buffered
        self._deferred_data = [[] for _ in range(len(self._input_info))]

    def _write_deferred_data(self):
        for src, info in zip(self._deferred_data, self._input_info):
            if "writer" in info and len(src):
                writer = info["writer"]
                for data in src:
                    writer.write(data, self.default_timeout)
        self._deferred_data = []
        self._input_ready = True

    def _write_stream_bytes(
        self,
        converter: ToBytesCallable,
        stream_id: int,
        data: RawDataBlob,
        timeout: float | None,
    ):
        """write a raw media data to a specified stream (backend)"""

        b = converter(obj=data)
        if not len(b):
            return

        if self._input_ready is True:
            logger.debug("[writer main] writing...")

            try:
                self._input_info[stream_id]["writer"].write(b, timeout)
            except (KeyError, BrokenPipeError, OSError):
                if self._logger:
                    self._logger.join_and_raise()

        else:
            # need to collect input data type and shape from the actual data
            # before starting the FFmpeg

            configure.update_raw_input(
                self._args["ffmpeg_args"], self._input_info, stream_id, data
            )

            self._deferred_data[stream_id].append(b)
            self._input_ready[stream_id] = True

            if all(self._input_ready):
                # once data is written for all the necessary inputs,
                # analyze them and start the FFmpeg
                self._open(True)

    @property
    def input_types(self) -> dict[int, MediaType | None]:
        """media type associated with the input streams"""
        return {
            i: v["media_type"] if "media_type" in v else None
            for i, v in enumerate(self._input_info)
        }

    @property
    def input_rates(self) -> dict[int, int | Fraction | None]:
        """sample or frame rates associated with the input streams"""
        return {
            i: v["raw_info"][2] if "raw_info" in v else None
            for i, v in enumerate(self._input_info)
        }

    @property
    def input_dtypes(self) -> dict[int, DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""
        return {
            i: v["raw_info"][0] if "raw_info" in v else None
            for i, v in enumerate(self._input_info)
        }

    @property
    def input_shapes(self) -> dict[int, ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""
        return {
            i: v["raw_info"][1] if "raw_info" in v else None
            for i, v in enumerate(self._input_info)
        }


class SimpleWriterBase(BaseEncodedOutputsMixin, BaseRawInputMixin, BaseFFmpegRunner):
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

    def _assign_pipes(self):

        configure.assign_input_pipes(
            self._args["ffmpeg_args"],
            self._output_info,
            self._args["sp_kwargs"],
            use_std_pipes=True,
        )

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
