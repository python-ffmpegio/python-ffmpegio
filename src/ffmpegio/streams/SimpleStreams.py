"""SimpleStreams Module: FFmpeg"""

from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import Unpack, Literal
from collections.abc import Sequence
from .._typing import (
    DTypeString,
    ShapeTuple,
    ProgressCallable,
    RawDataBlob,
    FFmpegOptionDict,
    InputInfoDict,
    RawOutputInfoDict,
    FromBytesCallable,
    CountDataCallable,
    ToBytesCallable,
)

from fractions import Fraction
from math import prod

from .. import configure, plugins
from ..stream_spec import stream_spec_to_map_option, StreamSpecDict
from ..errors import FFmpegioError
from ..configure import FFmpegArgs, MediaType, FFmpegUrlType, InitMediaOutputsCallable
from .BaseFFmpegRunner import BaseFFmpegRunner
from .._utils import get_bytesize

# fmt:off
__all__ = [ "SimpleReader", "SimpleWriter"]
# fmt:on


# info["reader"].read(n, timeout)
# info["writer"].write(None, None if timeout is None else timeout - time())


class SimpleReader(BaseFFmpegRunner):
    """queue-less SISO media reader class"""

    def __init__(
        self,
        *,
        init_kws,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        sp_kwargs: dict | None = None,
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
        :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
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
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            sp_kwargs={**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
            blocksize=blocksize,
            ref_output=0,
        )

        self._converter = from_bytes
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
        return self._output_info[0].get("user_map", None)

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

    def output_bytesize(self) -> int | None:
        """number of bytes per output sample/pixel"""
        return get_bytesize(self.output_shape, self.output_dtype)

    @property
    def output_labels(self) -> list[str | None]:
        """FFmpeg/custom labels of output streams"""
        return [self._output_info[0].get("user_map", None)]

    @property
    def output_types(self) -> list[MediaType | None]:
        """media type associated with the output streams (key)"""
        return [self._output_info[0]["media_type"]]

    @property
    def output_rates(self) -> list[int | Fraction | None]:
        """sample or frame rates associated with the output streams (key)"""
        info = self._output_info[0]
        return [info["raw_info"][2] if "raw_info" in info else None]

    @property
    def output_dtypes(self) -> list[DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""
        info = self._output_info[0]
        return [info["raw_info"][0] if "raw_info" in info else None]

    @property
    def output_shapes(self) -> list[ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""
        info = self._output_info[0]
        return [info["raw_info"][1] if "raw_info" in info else None]

    @property
    def output_counts(self) -> list[int]:
        """number of frames/samples read"""
        return [self._n0]

    @property
    def output_bytesizes(self) -> list[int | None]:
        """number of bytes per output sample/pixel"""
        return [get_bytesize(self.output_shape, self.output_dtype)]

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
        F = self.read(self._blocksize)
        if plugins.get_hook().is_empty(obj=F):
            raise StopIteration
        return F

    def read(self, n: int, squeeze: bool = False) -> RawDataBlob:
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
        nbytes = self.output_bytesize
        assert nbytes is not None

        dtype, shape, _ = info["raw_info"]  # type: ignore

        b = self._proc.stdout.read(n * nbytes if n >= 0 else -1)  # type: ignore
        data = converter(b=b, dtype=dtype, shape=shape, squeeze=squeeze)

        # update the frame/sample counter
        n = len(b) // nbytes  # actual number read
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
        assert "raw_info" in info
        shape = info["raw_info"][1]

        return self._proc.stdout.readinto(self._memoryviewer(obj=array)) // prod(  # type: ignore
            shape[1:]
        )


###########################################################################


class SimpleWriter(BaseFFmpegRunner):
    def __init__(
        self,
        # **init_kws,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Queue-less simple media writer

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg input option dicts with zero or one streaming pipe. (only one in input or output)
        :param output_info: FFmpeg output option dicts with zero or one any streaming pipe. (only one in input or output)
        :param input_ready: True to start FFmpeg, if not provide a list of per-stream readiness
        :param init_deferred_outputs: function to initialize the outputs which have been deferred to
                                      configure until the first batch of input data is in
        :param deferred_output_args:
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        # add std writer

        super().__init__(
            ffmpeg_args=ffmpeg_args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=init_deferred_outputs,
            deferred_output_args=deferred_output_args,
            timeout=timeout,
            progress=progress,
            show_log=show_log,
            sp_kwargs={**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
            ref_output=0,
        )

        self._converter = from_bytes
        self._memoryviewer = to_memoryview

        # set the default read block size for the reference stream
        info = self._input_info[0]
        assert "raw_info" in info

        self._rate = info["raw_info"][2]
        self._n0 = 0  # timestamps of the last read sample

        ############

        # input data must be initially buffered
        self._deferred_data = []

    def _write_deferred_data(self):
        self._proc.stdin.write(self._deferred_data[0])
        self._deferred_data = []
        self._input_ready = True

    def _assign_pipes(self):

        configure.assign_input_pipes(
            self._args["ffmpeg_args"],
            self._input_info,
            self._args["sp_kwargs"],
            use_std_pipes=True,
        )

    @property
    def input_type(self) -> MediaType | None:
        """media type associated with the input streams"""
        info = self._input_info[0]
        return info.get("media_type", None)

    @property
    def input_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the input streams"""
        info = self._input_info[0]
        return info["raw_info"][2] if "raw_info" in info else None

    @property
    def input_dtype(self) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""
        info = self._input_info[0]
        return info["raw_info"][0] if "raw_info" in info else None

    @property
    def input_shape(self) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""
        info = self._input_info[0]
        return info["raw_info"][1] if "raw_info" in info else None

    @property
    def input_count(self) -> int:
        """number of input frames/samples written"""
        return self._n0

    @property
    def input_bytesize(self) -> int | None:
        """input sample/pixel count per frame"""
        return get_bytesize(self.input_shape, self.input_dtype)

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

        b = self._get_bytes(obj=data)
        if not len(b):
            return

        if self._input_ready is True:
            logger.debug("[writer main] writing...")
            try:
                self._proc.stdin.write(b)
            except (BrokenPipeError, OSError):
                self._logger.join_and_raise()

        else:
            # need to collect input data type and shape from the actual data
            # before starting the FFmpeg

            configure.update_raw_input(
                self._args["ffmpeg_args"], self._input_info, 0, data
            )

            self._deferred_data.append(b)
            self._input_ready = True

            if self._input_ready is True:
                # once data is written for all the necessary inputs,
                # analyze them and start the FFmpeg
                self._open(True)

    def flush(self):
        self._proc.stdin.flush()
