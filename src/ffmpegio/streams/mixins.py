from __future__ import annotations

import logging

from contextlib import ExitStack
from fractions import Fraction

from typing_extensions import Callable, Literal

from .. import configure, probe

from .._typing import (
    InputInfoDict,
    OutputInfoDict,
    InputPipeInfoDict,
    OutputPipeInfoDict,
    FFmpegOptionDict,
    RawDataBlob,
    ShapeTuple,
    DTypeString,
    MediaType,
)

from ..configure import MediaType
from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError
from .._typing import FromBytesCallable, CountDataCallable, ToBytesCallable

logger = logging.getLogger("ffmpegio")

__all__ = [
    "BaseRawInputsMixin",
    "BaseRawOutputsMixin",
    "BaseEncodedInputsMixin",
    "BaseEncodedOutputsMixin",
]


class BaseInputsMixin:
    """write a raw media data to a specified stream (backend)"""

    _init_kws: dict
    _piped_inputs: dict[int, Literal["input_urls", "input_stream_args", "extra_input"]]
    _input_info: list[InputInfoDict] | None
    _input_pipes: list[InputPipeInfoDict] | None
    _logger: LoggerThread | None
    _open: Callable[[bool], None]
    _args: dict

    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)

    #     # input data must be initially buffered
    #     self._deferred_data = [[] for _ in range(len(self._input_info))]

    @property
    def input_types(self) -> dict[int, MediaType | Literal["encoded"]]:
        """input piped types (lists both encoded and raw media pipes)

        - only piped inputs are returned
        - integer keys is the unique input index (this index is not contiguous
          if non-piped inputs are also used.)
        - values are either 'video' or 'audio' if raw media stream or 'encoded'
          if encoded byte stream

        """

        kws = self._init_kws
        return {
            i: (
                "encoded"
                if kw in ("input_urls", "extra_inputs")
                else {"a": "audio", "v": "video"}[kws["input_stream_types"][i]]
            )
            for i, kw in self._piped_inputs.items()
        }

    @property
    def input_rates(self) -> dict[int, int | Fraction]:
        """audio sample or video frame rates associated with the input media streams"""
        kws = self._init_kws
        return {
            i: kws["input_stream_args"][i][1][
                {"a": "ar", "v": "r"}[kws["input_stream_types"][i]]
            ]
            for i, kw in self._piped_inputs.items()
            if kw == "input_stream_args"
        }

    def _write_deferred_data(self):
        for data, info in zip(self._deferred_data, self._input_info):
            if len(data) and "writer" in info:
                info["writer"].write(data, self.default_timeout)
        self._deferred_data = []
        self._input_ready = True

    def _write_encoded_stream(
        self,
        index: int,
        info: OutputInfoDict,
        data: bytes,
        timeout: float | None,
    ):
        """write a raw media data to a specified stream (backend)"""

        if self._input_ready is True:
            try:
                info["writer"].write(data, timeout)
            except:
                raise FFmpegioError("Cannot write to a non-piped input.")

        else:

            # buffer must be contiguous
            data0 = self._deferred_data[index]
            if len(data0):
                data0.append(data)

            else:
                self._deferred_data[index] = [data]

            # need to be able to probe the input streams before starting the FFmpeg
            try:
                probe.format_basic(data)
            except FFmpegError:
                pass  # not ready yet
            else:
                self._input_ready[index] = True

            if all(self._input_ready):
                # once data is written for all the necessary inputs,
                # analyze them and start the FFmpeg
                self._open(True)


class BaseRawInputsMixin(BaseInputsMixin):
    """write a raw media data to a specified stream (backend)"""

    default_timeout: float | None
    _input_info: list[InputInfoDict]
    _output_info: list[OutputInfoDict]
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
    def input_dtypes(self) -> dict[int, DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""
        kws = self._init_kws
        if self._input_info is not None:
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
        if self._input_info is not None:
            return {
                i: v["raw_info"][1]
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


class BaseRawOutputsMixin:

    default_timeout: float | None
    _input_info: list[InputInfoDict]
    _output_info: list[OutputInfoDict]
    _deferred_data: list[list[bytes]]
    _input_ready: bool
    _logger: LoggerThread | None

    def __init__(self, blocksize, ref_output, **kwargs):
        super().__init__(**kwargs)

        # set the default read block size for the reference stream
        self._blocksize = blocksize
        self._ref = ref_output
        self._rates = None
        self._n0 = None  # timestamps of the last read sample

    @property
    def output_labels(self) -> list[str | None]:
        """FFmpeg/custom labels of output streams"""
        return [
            v.get("user_map", None) or f"{i}" for i, v in enumerate(self._output_info)
        ]

    @property
    def output_types(self) -> list[MediaType | None]:
        """media type associated with the output streams (key)"""
        return [v["media_type"] for v in self._output_info]

    @property
    def output_rates(self) -> list[int | Fraction | None]:
        """sample or frame rates associated with the output streams (key)"""

        def get_rate(v):
            return v and v[2]

        return [get_rate(v) for v in self._output_info]

    @property
    def output_dtypes(self) -> list[DTypeString | None]:
        """frame/sample data type associated with the output streams (key)"""

        def get_dtype(v):
            return v and v[1]

        return [get_dtype(v) for v in self._output_info]

    @property
    def output_shapes(self) -> list[ShapeTuple | None]:
        """frame/sample shape associated with the output streams (key)"""

        def get_shape(v):
            return v and v[0]

        return [get_shape(v) for v in self._output_info]

    @property
    def output_counts(self) -> list[int]:
        """number of frames/samples read"""
        return [0] * len(self._output_info) if self._n0 is None else list(self._n0)

    def _init_pipes(self) -> ExitStack:

        # set the default read block size for the referenc stream
        info = self._output_info[self._ref]
        if self._blocksize is None:
            self._blocksize = 1 if info["media_type"] == "video" else 1024
        self._rates = self.output_rates

        if any(r is None for r in self._rates):
            raise FFmpegioError("There is an output stream without known output rate.")

        self._n0 = [0] * len(self._output_info)  # timestamps of the last read sample
        self._pipe_kws = {
            **self._pipe_kws,
            "update_rate": self._rates[self._ref] / Fraction(self._blocksize),
        }

        # set up and activate pipes and read/write threads
        return super()._init_pipes()

    def _read_stream_bytes(
        self,
        converter: FromBytesCallable,
        counter: CountDataCallable,
        dtype: DTypeString,
        shape: ShapeTuple,
        info: OutputInfoDict,
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


class BaseEncodedOutputsMixin:

    default_timeout: float | None
    _input_info: list[InputInfoDict]
    _output_info: list[OutputInfoDict]
    _deferred_data: list[list[bytes]]
    _input_ready: bool
    _logger: LoggerThread

    def __init__(self, blocksize, **kwargs):
        super().__init__(**kwargs)

        # set the default read block size
        self._blocksize = blocksize

    def _init_pipes(self) -> ExitStack:

        # set the default read block size for the referenc stream
        self._pipe_kws = {**self._pipe_kws, "blocksize": self._blocksize}

        # set up and activate pipes and read/write threads
        return super()._init_pipes()

    def _read_encoded_stream(
        self,
        info: OutputInfoDict,
        n: int,
        timeout: float | None = None,
    ) -> bytes:
        """read selected output stream (shared backend)"""

        return info["reader"].read(n, timeout)
