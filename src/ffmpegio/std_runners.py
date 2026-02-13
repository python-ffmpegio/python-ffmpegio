"""FFmpeg runner functions for SISO operations over standard pipes"""

from __future__ import annotations

import logging

from . import configure
from . import ffmpegprocess as fp
from ._typing import (
    TYPE_CHECKING,
    Any,
    EncodedInputInfoDict,
    EncodedOutputInfoDict,
    ProgressCallable,
    RawInputInfoDict,
    RawOutputInfoDict,
)
from .errors import FFmpegError, FFmpegioError

if TYPE_CHECKING:
    from .configure import FFmpegArgs

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

    out = fp.run(
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
    progress,
    overwrite,
    show_log,
    sp_kwargs,
    args,
    input_info,
    output_info,
    two_pass=False,
    pass1_omits=None,
    pass1_extras=None,
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

    if two_pass:
        if pass1_omits is not None:
            kwargs["pass1_omits"] = pass1_omits
        if pass1_extras is not None:
            kwargs["pass1_extras"] = pass1_extras

    out = (fp.run_two_pass if two_pass else fp.run)(
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
