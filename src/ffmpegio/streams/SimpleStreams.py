"""SimpleStreams Module: FFmpeg"""

from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import Unpack, Literal
from collections.abc import Sequence
from .._typing import (
    overload,
    Callable,
    Iterator,
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

from .._utils import get_bytesize
from .. import configure, plugins
from ..stream_spec import stream_spec_to_map_option, StreamSpecDict
from ..errors import FFmpegioError
from ..configure import (
    FFmpegArgs,
    MediaType,
    FFmpegUrlType,
    InitMediaOutputsCallable,
    init_media_read,
    init_media_write,
    MediaReadKwsDict,
    MediaWriteKwsDict,
    FFmpegInputOptionTuple,
)
from .BaseFFmpegRunner import BaseFFmpegRunner
from .mixins import (
    BaseRawInputsMixin,
    BaseRawOutputsMixin,
)

# fmt:off
__all__ = [ "SimpleReader", "SimpleWriter"]
# fmt:on


# info["reader"].read(n, timeout)
# info["writer"].write(None, None if timeout is None else timeout - time())


class StdFFmpegRunner(BaseFFmpegRunner):
    """Base class to run FFmpeg only with one std pipe"""

    _use_std_pipes: bool = True

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

        For ``StdFFmpegRunner``, the number of pipes is validated (1 raw
        output and no encoded input or output)

        """

        ready = super()._try_config_ffmpeg(stream, data)
        if ready:  # validate
            ninputs = sum(
                info["src_type"] in ("buffer", "fileobj") for info in self._input_info
            )
            noutputs = sum(
                info["dst_type"] in ("buffer", "fileobj") for info in self._output_info
            )

            if ninputs + noutputs > 1:
                raise FFmpegioError(
                    "Only 1 pipe (stdin OR stdout) can be used in StdFFmpegRunner."
                )

        return ready


class SimpleReader(BaseRawOutputsMixin, StdFFmpegRunner):
    """queue-less SISO media reader class"""

    @overload
    def __init__(
        self,
        input_urls: list[FFmpegInputOptionTuple],
        output_options: FFmpegOptionDict,
        options: FFmpegOptionDict | None = None,
        squeeze: bool = True,
        extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
        blocksize: int | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """create a single-pipe media reader

        :param input_urls: list of input urls
        :param output_stream: dict of FFmpeg output options. One of it items must
                              be the ``'map'`` option to uniquely specify a stream.
        :param options: optional ffmpeg option dict including input, output, and
                        global options. For input options, append '_in' to the
                        end of ffmpeg option names.
        :param squeeze: ``True`` (default) to eliminate raw output's singleton
                        dimensions. Use ``False`` to always return 2D array for
                        audio and 4D array for video.
        :param extra_outputs: extra encoded output urls, Each element is a tuple
                              pair of url and output option dict. The url must be
                              a url and not pipes or pipe objects.
        :param blocksize: read block size (in frames for video or samples
                          in audio) when the reader object is used as an iterator
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        """

    def __init__(
        self,
        input_urls: list[FFmpegInputOptionTuple],
        output_options: FFmpegOptionDict,
        options: FFmpegOptionDict | None = None,
        extra_outputs: list[FFmpegOutputOptionTuple] | None = None,
        squeeze: bool = True,
        **kwargs,
    ):

        super().__init__(
            init_func=init_media_read,
            init_kws={
                "input_urls": input_urls,
                "output_streams": [output_options],
                "options": options or {},
                "extra_outputs": extra_outputs,
                "squeeze": squeeze,
            },
            **kwargs,
        )

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

        For ``SimpleReader``, the number of pipes is validated (1 raw
        output and no encoded input or output)

        """

        ready = super()._try_config_ffmpeg(stream, data)
        if ready:  # validate

            is_raw = next(
                "media_type" in info
                for info in self._output_info
                if info["dst_type"] == "buffer"
            )
            if not is_raw:
                raise FFmpegioError("The output stream must a raw media stream.")

        return ready

    @property
    def output_label(self) -> str | None:
        """FFmpeg/custom labels of output streams"""
        olabels = self.output_labels
        return None if olabels is None else olabels[0]

    @property
    def output_type(self) -> MediaType | None:
        """media type associated with the output streams (key)"""
        otypes = self.output_types
        return None if otypes is None else otypes[0]

    @property
    def output_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the output streams (key)"""
        orates = self.output_rates
        return None if orates is None else orates[0]

    @property
    def _output_rate(self) -> int | Fraction | None:
        return self.output_rate

    @property
    def output_dtype(self) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""
        odtypes = self.output_dtypes
        return None if odtypes is None else odtypes[0]

    @property
    def output_shape(self) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""
        oshapes = self.output_shapes
        return None if oshapes is None else oshapes[0]

    def read(self, n: int) -> RawDataBlob:
        """Read and return a raw data blob (e.g., a numpy.ndarray if
        ``ffmpegio.use('numpy')``) containing up to n frames/samples. If
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

        return self._read_raw(0, n)


###########################################################################


class SimpleWriter(BaseRawInputsMixin, StdFFmpegRunner):
    """single-pipe media writer"""

    @overload
    def __init__(
        self,
        output_urls: list[FFmpegOutputOptionTuple],
        input_stream_type: Literal["a", "v"],
        input_stream_options: FFmpegOptionDict,
        options: FFmpegOptionDict | None = None,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        extra_inputs: list[FFmpegInputOptionTuple] | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        overwrite: bool | None = None,
        sp_kwargs: dict | None = None,
    ):
        """single-pipe media writer

        :param output_urls: pairs of output url and options
        :param input_stream_type: specify raw media input type
        :param input_stream_options: ffmpeg input options for the raw media input
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

    def __init__(
        self,
        output_urls: list[FFmpegOutputOptionTuple],
        input_stream_type: Literal["a", "v"],
        input_stream_options: FFmpegOptionDict,
        options: FFmpegOptionDict | None = None,
        input_dtype: DTypeString | None = None,
        input_shape: ShapeTuple | None = None,
        extra_inputs: list[FFmpegInputOptionTuple] | None = None,
        **kwargs,
    ):
        super().__init__(
            init_func=init_media_write,
            init_kws={
                "output_urls": output_urls,
                "input_stream_types": [input_stream_type],
                "input_stream_args": [(None, input_stream_options)],
                "extra_inputs": extra_inputs,
                "options": options or {},
                "input_dtypes": input_dtype and [input_dtype],
                "input_shapes": input_shape and [input_shape],
            },
            **kwargs,
        )

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

        For ``SimpleReader``, the number of pipes is validated (1 raw
        output and no encoded input or output)

        """

        ready = super()._try_config_ffmpeg(stream, data)
        if ready:  # validate

            is_raw = next(
                "media_type" in info
                for info in self._input_info
                if info["src_type"] == "buffer"
            )
            if not is_raw:
                raise FFmpegioError("The input stream must a raw media stream.")

    @property
    def input_type(self) -> MediaType | None:
        """media type associated with the input streams"""
        vals = self.input_types
        return None if vals is None else vals[0]

    @property
    def input_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the input streams"""
        vals = self.input_rates
        return None if vals is None else vals[0]

    @property
    def input_dtype(self) -> DTypeString | None:
        """frame/sample data type of the input stream"""
        vals = self.input_dtypes
        return None if vals is None else vals[0]

    @property
    def input_shape(self) -> ShapeTuple | None:
        """frame/sample shape of the input stream"""
        vals = self.input_shapes
        return None if vals is None else vals[0]

    # @property
    # def input_count(self) -> int:
    #     """number of input frames/samples written"""
    #     return self._n0

    def write(self, data: RawDataBlob):
        """Write the given numpy.ndarray object, data, and return the number
        of bytes written (always equal to the number of data frames/samples,
        since if the write fails an OSError will be raised).

        When in non-blocking mode, a BlockingIOError is raised if the data
        needed to be written to the raw stream but it couldn’t accept all
        the data without blocking.

        The caller may release or mutate data after this method returns,
        so the implementation should only access data during the method call.

        """

        if self._status == self._status.BUFFERING:
            if self._try_config_ffmpeg(0, data):
                self._run_ffmpeg(True)
        else:
            self._write_raw(0, data)
