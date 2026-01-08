from __future__ import annotations

import logging

from contextlib import ExitStack
from fractions import Fraction

from typing_extensions import Callable, Literal

from .. import configure, probe, stream_spec, utils

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

from ..threading import LoggerThread
from ..errors import FFmpegError, FFmpegioError
from .._typing import FromBytesCallable, CountDataCallable, ToBytesCallable
from .BaseFFmpegRunner import FFmpegStatus

logger = logging.getLogger("ffmpegio")

__all__ = [
    "BaseRawInputsMixin",
    "BaseRawOutputsMixin",
    "BaseEncodedInputsMixin",
    "BaseEncodedOutputsMixin",
]


class BaseInputsMixin:
    """backend mixin for encoded media writer and transcoder"""

    _status: FFmpegStatus
    _init_kws: dict
    _piped_inputs: dict[int, Literal["input_urls", "input_stream_args", "extra_input"]]
    _input_info: list[InputInfoDict] | None
    _input_pipes: list[InputPipeInfoDict] | None

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

    def _write_encoded(self, index: int, data: bytes):
        """backend mixin for raw media writer and filter"""

        try:
            info = self._input_pipes[index]
            assert "media_type" not in self._input_info[index]
            info["writer"].write(data)
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Input Stream #{index} is not an encoded stream.") from e


class BaseRawInputsMixin(BaseInputsMixin):
    """write a raw media data to a specified stream (backend)"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # input data must be initially buffered
        self._deferred_data = [[] for _ in range(len(self._input_info))]

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


class BaseOutputsMixin:

    _status: FFmpegStatus
    _init_kws: configure.FFmpegMediaKwsDict
    _output_info: list[OutputInfoDict] | None
    _output_pipes: list[OutputPipeInfoDict] | None

    _nb_outputs: tuple[int, int] = (0, 0)  # (raw, raw+encoded)

    # def __init__(self, blocksize, **kwargs):
    #     super().__init__(**kwargs)

    #     # set the default read block size
    #     self._blocksize = blocksize

    @property
    def output_types(self) -> dict[int, MediaType | Literal["encoded"]] | None:
        """output piped types (lists both encoded and raw media pipes)

        - only piped inputs are returned
        - integer keys is the unique input index (this index is not contiguous
          if non-piped inputs are also used.)
        - values are either 'video' or 'audio' if raw media stream or 'encoded'
          if encoded byte stream

        """

        if self._output_pipes is None:
            # not yet running, deducible only if only encoded outputs or well-defined input arguments
            kws = self._init_kws

            if "output_streams" in kws:  # raw output streams (+extra encoded)
                kw = kws["output_streams"]
                if kw is None:
                    return None

                outtypes = {}
                for i, (_, opts) in enumerate(
                    kw if isinstance(kw, list) else iter(v[1] for v in kw.values())
                ):
                    mapopts = stream_spec.parse_map_option(
                        opts["map"], input_file_id=0, parse_stream=True
                    )
                    if "stream_specifier" not in mapopts:
                        return None
                    media_type = stream_spec.is_unique_stream(
                        mapopts["stream_specifier"]
                    )
                    if media_type is False:
                        return None
                    outtypes[i] = media_type

                if "extra_outputs" in kws:  # encoded output also specified
                    nout = len(kw)
                    for i, (url, _) in enumerate(kws["extra_outputs"]):
                        if utils.is_pipe(url):
                            outtypes[i + nout] = "encoded"

            return outtypes
        else:
            info = self._output_info
            return {i: info[i].get("media_type", "encoded") for i in self._output_pipes}

    def _read_encoded(self, index: int, n: int) -> bytes:
        """read selected output stream (shared backend)"""

        try:
            info = self._output_pipes[index]
            assert "media_type" not in self._output_info[index]
            return info["reader"].read(n)
        except AttributeError as e:
            raise FFmpegioError(f"FFmpeg is not running yet.") from e
        except (KeyError, AssertionError) as e:
            raise ValueError(f"Output Stream #{index} is not an encoded stream.") from e


class BaseRawOutputsMixin(BaseOutputsMixin):

    _init_kws: configure.MediaReadKwsDict | configure.MediaFilterKwsDict

    _status: FFmpegStatus
    _output_info: list[OutputInfoDict] | None
    _output_pipes: list[OutputPipeInfoDict] | None

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

    def _read_raw(self, index: int, n: int) -> RawDataBlob:
        """read selected output stream (shared backend)"""

        data = converter(
            b=info["reader"].read(n, timeout), dtype=dtype, shape=shape, squeeze=squeeze
        )

        # update the frame/sample counter
        n = counter(obj=data)  # actual number read
        self._n0[stream_id] += n

        return data
