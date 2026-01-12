from __future__ import annotations

import logging

from contextlib import ExitStack
from fractions import Fraction
from abc import ABCMeta, abstractmethod

from typing_extensions import Callable, Literal

from .. import configure, probe, stream_spec, utils

from .._typing import (
    OutputInfoDict,
    InputPipeInfoDict,
    PipedEncodedInputInfoDict,
    RawInputInfoDict,
    OutputPipeInfoDict,
    RawOutputInfoDict,
    EncodedOutputInfoDict,
    RawDataBlob,
    ShapeTuple,
    DTypeString,
    MediaType,
)

from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError
from .._typing import FromBytesCallable, CountDataCallable, ToBytesCallable
from .BaseFFmpegRunner import FFmpegStatus, BaseFFmpegRunner

logger = logging.getLogger("ffmpegio")

__all__ = [
    "BaseRawInputsMixin",
    "BaseRawOutputsMixin",
]


class BaseRawInputsMixin:
    """write a raw media data to a specified stream (backend)"""

    _status: FFmpegStatus
    _init_kws: dict
    _piped_inputs: dict[int, Literal["input_urls", "input_stream_args", "extra_input"]]
    _input_info: list[RawInputInfoDict]
    _input_pipes: list[InputPipeInfoDict]

    @property
    def input_rates(self) -> dict[int, int | Fraction | None]:
        """audio sample or video frame rates associated with the input media streams"""
        kws = self._init_kws
        return {
            i: kws["input_stream_args"][i][1][
                {"a": "ar", "v": "r"}[kws["input_stream_types"][i]]
            ]
            for i, kw in self._piped_inputs.items()
            if kw == "input_stream_args"
        }

    @property
    def input_dtypes(self) -> dict[int, DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""
        kws = self._init_kws
        if self._args_not_ready:
            return {
                i: v["raw_info"][0]
                for i, v in enumerate(self._input_info)
                if "raw_info" in v
            }
        elif "input_dtypes" in kws:  # dtypes maybe given
            dtypes = kws["input_dtypes"]
            return {
                i: dtypes[i]
                for i, kw in self._piped_inputs.items()
                if kw == "input_stream_args"
            }
        else:
            # not known yet
            return {
                i: None
                for i, kw in self._piped_inputs.items()
                if kw == "input_stream_args"
            }

    @property
    def input_shapes(self) -> dict[int, ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""
        kws = self._init_kws
        if self._args_not_ready:
            # ffmpeg configured
            return {
                i: v["raw_info"][1]
                for i, v in enumerate(self._input_info)
                if "raw_info" in v
            }
        elif "input_shapes" in kws:  # dtypes maybe given
            # pre-configure, given by user
            dtypes = kws["input_shapes"]
            return {
                i: dtypes[i]
                for i, kw in self._piped_inputs.items()
                if kw == "input_stream_args"
            }
        else:
            # pre-configure, not given by user
            return {
                i: None
                for i, kw in self._piped_inputs.items()
                if kw == "input_stream_args"
            }

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


################################################################################


class BaseRawOutputsMixin(metaclass=ABCMeta):

    _init_kws: configure.MediaReadKwsDict | configure.MediaFilterKwsDict
    _status: FFmpegStatus
    _output_info: list[RawOutputInfoDict]
    _output_pipes: list[OutputPipeInfoDict]

    _primary_output: int | str | None = None
    _read_size_in: int | None = None
    _read_size: int = 1

    def __init__(
        self,
        primary_output: int | str | None = None,
        blocksize: int | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._primary_output = primary_output

        # set the default read block size for the reference stream
        self._read_size_in = blocksize
        if blocksize is not None:
            self._read_size = blocksize

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

    @property
    def _output_rate(self) -> int | Fraction | None:
        return self.primary_output_rate

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

        For ``SimpleReader``, the number of piped outputs are validated (1 raw
        output and no encoded input or output)

        """

        ready = super()._try_config_ffmpeg(stream, data)

        if ready and self._read_size_in is None:  # set read size
            index = self.primary_output_index
            media_type = self._output_info[index]["media_type"]
            self._read_size = 1 if media_type == "video" else 1024

        return ready

    @property
    def output_rates(self) -> list[int | Fraction] | None:
        """sample or frame rates associated with the output streams (key)"""

        if self._args_not_ready:
            if not self._all_output_streams_defined:
                return None

            kws = self._init_kws

            if "output_streams" not in kws:  # raw output streams (+extra encoded)
                return []  # shouldn't get here

            kw = self._init_kws["output_streams"]
            rates = [
                kw[i][1].pop("r" if mtype == "video" else "ar", None)
                for i, mtype in self.output_types.items()
                if mtype != "encoded"
            ]

            return rates

        else:
            return [
                v["raw_info"][2] if "raw_info" in v else None for v in self._output_info
            ]

    @property
    def output_dtypes(self) -> dict[int, DTypeString] | None:
        """frame/sample data type associated with the output streams (key)"""

        if self._args_not_ready:
            if not self._all_output_streams_defined:
                return None

            if "output_streams" not in kws:  # raw output streams (+extra encoded)
                return {}

            kw = self._init_kws["output_streams"]
            dtypes = []
            for i, mtype in self.output_types.items():
                if mtype == "encoded":
                    # skip encoded output stream
                    continue

                opts = kw[i][1]

                if mtype == "video":
                    if "pix_fmt" in opts:
                        pix_fmt = opts["pix_fmt"]
                        dtypes[i] = utils.get_pixel_format(pix_fmt)[0]
                    else:
                        dtypes[i] = None
                else:  # if mtype=='audio'
                    if "sample_fmt" in opts:
                        sample_fmt = opts["sample_fmt"]
                        dtypes[i] = utils.get_audio_format(sample_fmt)[0]
                    else:
                        dtypes[i] = None

            return dtypes

        else:
            return [v["raw_info"][0] for v in self._iter_piped_output_info()]

    @property
    def output_shapes(self) -> list[ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""

        if self._args_not_ready:
            if not self._all_output_streams_defined:
                return None

            if "output_streams" not in kws:  # raw output streams (+extra encoded)
                return {}

            kw = self._init_kws["output_streams"]
            shapes = {}
            for i, mtype in self.output_types.items():
                if mtype == "encoded":
                    # skip encoded output stream
                    continue

                opts = kw[i][1]

                if mtype == "video":
                    if "pix_fmt" in opts:
                        pix_fmt = opts["pix_fmt"]
                        s = opts["s"]
                        shapes[i] = utils.get_video_format(pix_fmt, s)[1]
                    else:
                        shapes[i] = None
                else:  # if mtype=='audio'
                    has_opt = [k in opts for k in ("ac", "channel_layout", "ch_layout")]
                    if has_opt[0] or has_opt[1]:
                        layout = (
                            opts["channel_layout"] if has_opt[0] else opts["ch_layout"]
                        )
                        shapes[i] = (utils.layout_to_channels(layout),)
                    elif has_opt[2]:
                        shapes[i] = (int(opts["ac"]),)
                    else:
                        shapes[i] = None

            return shapes

        else:
            return [
                v["raw_info"][1] if "raw_info" in v else None
                for i, v in self._iter_piped_output_info()
            ]

    def output_sample_sizes(self) -> list[int] | None:
        if self._args_not_ready:
            return None

        return []

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._read_size)
        if self._output_info[self.primary_output_index]["data_is_empty"](obj=F):
            raise StopIteration
        return F

    @abstractmethod
    def read(self, n: int) -> RawDataBlob | dict[int | str, RawDataBlob]:
        """Read and return a raw data blob (e.g., a numpy.ndarray if
        ``ffmpegio.use('numpy')``) containing up to n frames/samples. If a
        reader outputs multiple raw streams, its output is a dict keyed by
        stream identifiers of raw data blobs.

        If the argument is omitted, None, or negative, data is read and
        returned until EOF is reached. An empty bytes object is returned
        if the stream is already at EOF.

        If the argument is positive, and the underlying raw stream is not
        interactive, multiple raw reads may be issued to satisfy the byte
        count (unless EOF is reached first). But for interactive raw streams,
        at most one raw read will be issued, and a short result does not
        imply that EOF is imminent.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

    @property
    def output_counts(self) -> list[int]:
        """number of frames/samples read"""
        return [0] * len(self._output_info) if self._n0 is None else list(self._n0)

    # @property
    # def output_counts(self) -> list[int]:
    #     """number of frames/samples read"""
    #     return [self._n0]

    # @property
    # def output_bytesizes(self) -> list[int | None]:
    #     """number of bytes per output sample/pixel"""
    #     return [get_bytesize(self.output_shape, self.output_dtype)]

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
        b = self._output_pipes[index]["reader"].read(
            n * self.output_samplesizes[index] if n > 0 else n
        )

        data = info["bytes2data"](
            b=b, dtype=dtype, shape=shape, squeeze=info["squeeze"]
        )

        # update the frame/sample counter
        # n = counter(obj=data)  # actual number read
        # self._n0[stream_id] += n

        return data
