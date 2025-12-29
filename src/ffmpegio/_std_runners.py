"""FFmpeg runner functions for SISO operations over standard pipes"""

from __future__ import annotations

import logging

from . import (
    ffmpegprocess,
    configure,
    FFmpegError,
    FFmpegioError,
    plugins,
    analyze,
)
from .utils import log as log_utils
from ._typing import (
    Sequence,
    TYPE_CHECKING,
    Buffer,
    Any,
    ProgressCallable,
    FFmpegUrlType,
    FFmpegOptionDict,
    RawDataBlob,
    RawInputInfoDict,
    EncodedInputInfoDict,
    RawOutputInfoDict,
    EncodedOutputInfoDict,
)

if TYPE_CHECKING:
    from .configure import (
        FFmpegInputOptionTuple,
        FFmpegInputUrlComposite,
        FFmpegInputUrlNoPipe,
        FFmpegNoPipeInputOptionTuple,
        FFmpegOutputOptionTuple,
        FFmpegOutputUrlNoPipe,
        FFmpegNoPipeOutputOptionTuple,
        FFmpegArgs,
    )
    from .filtergraph.abc import FilterGraphObject
    from .utils.concat import FFConcat

logger = logging.getLogger("ffmpegio")

__all__ = ["run_and_return_raw", "run_and_return_encoded"]


def run_and_return_raw(
    args: FFmpegArgs,
    input_info: list[RawInputInfoDict | EncodedInputInfoDict],
    output_info: list[RawOutputInfoDict | EncodedOutputInfoDict],
    progress: ProgressCallable | None,
    show_log: bool | None,
    sp_kwargs: dict[str, Any] | None,
):

    # check configuration yields at most one piped input
    # check configuration yields at most one piped output
    n_piped_inputs = sum(
        info["src_type"] in ("buffer", "fileobj") for info in input_info
    )
    if n_piped_inputs > 1:
        raise ValueError(
            "Only at most one input source can be a pipe or a file-stream object."
        )

    # check configuration yields exactly one piped audio output
    if len(output_info) == 0:
        raise FFmpegioError("No audio stream found.")
    if len(output_info) > 1:
        raise ValueError("Too many audio stream found.")
    if output_info[0]["media_type"] != "audio":
        raise ValueError("Mapped stream is not an audio stream.")
    if output_info[0]["dst_type"] != "buffer":
        raise ValueError("Not outputting to pipe")

    n_piped_outputs = sum(
        info["dst_type"] in ("buffer", "fileobj") for info in output_info
    )
    if n_piped_outputs > 1:
        raise ValueError(
            "Only at most one output destination can be a pipe or a file-stream object."
        )

    # assign the stdin and stdout pipes
    kwargs = {
        **configure.assign_input_pipes(args, input_info, True, True)[1],
        **configure.assign_output_pipes(args, output_info, True)[1],
    }

    if sp_kwargs is not None:
        # ignore user's stdin, stdout, stdout if specified
        kwargs = {**sp_kwargs, **kwargs}

    out = ffmpegprocess.run(
        args,
        progress=progress,
        capture_log=None if show_log else True,
        **kwargs,
    )
    if out.returncode:
        raise FFmpegError(out.stderr, show_log)

    oinfo = output_info[0]
    dtype, shape, rate = oinfo["raw_info"]

    return rate, oinfo["bytes2data"](
        b=out.stdout, dtype=dtype, shape=shape, squeeze=oinfo["squeeze"]
    )


def run_and_return_encoded(
    progress, overwrite, show_log, sp_kwargs, args, input_info, output_info
):
    if output_info is None:
        raise FFmpegioError("Unknown error occurred to complete FFmpeg configuration.")

    # check configuration yields at most one piped output
    n_piped_inputs = sum(
        info["src_type"] in ("buffer", "fileobj") for info in input_info
    )
    if n_piped_inputs > 1:
        raise ValueError(
            "Only at most one input source can be a pipe or a file-stream object."
        )

    n_piped_outputs = sum(
        info["dst_type"] in ("buffer", "fileobj") for info in output_info
    )
    if n_piped_outputs > 1:
        raise ValueError(
            "Only at most one output destination can be a pipe or a file-stream object."
        )

    # assign the stdin and stdout pipes
    kwargs = {
        **configure.assign_input_pipes(args, input_info, True, True)[1],
        **configure.assign_output_pipes(args, output_info, True)[1],
    }

    if sp_kwargs is not None:
        # ignore user's stdin, stdout, stdout if specified
        kwargs = {**sp_kwargs, **kwargs}

    out = ffmpegprocess.run(
        args,
        progress=progress,
        capture_log=None if show_log else True,
        overwrite=overwrite,
        **kwargs,
    )
    if out.returncode:
        raise FFmpegError(out.stderr, show_log)

    if n_piped_outputs and any(info["dst_type"] == "buffer" for info in output_info):
        return out.stdout
