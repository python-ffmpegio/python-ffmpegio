from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from ._typing import Sequence, ProgressCallable, Unpack, FFmpegOptionDict
from .configure import (
    FFmpegOutputUrlComposite,
    FFmpegInputUrlComposite,
    FFmpegInputOptionTuple,
    FFmpegOutputOptionTuple,
)


from . import ffmpegprocess as fp, configure, utils, FFmpegError
from .path import check_version

__all__ = ["transcode"]


def transcode(
    inputs: (
        FFmpegInputUrlComposite
        | Sequence[FFmpegInputUrlComposite | FFmpegInputOptionTuple]
    ),
    outputs: (
        FFmpegOutputUrlComposite
        | Sequence[FFmpegOutputUrlComposite | FFmpegOutputOptionTuple]
    ),
    *,
    progress: ProgressCallable | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    two_pass: bool = False,
    pass1_omits: (
        Sequence[str] | Sequence[Sequence[str]] | dict[int, Sequence[str]] | None
    ) = None,
    pass1_extras: (
        FFmpegOptionDict
        | Sequence[FFmpegOptionDict]
        | dict[int, FFmpegOptionDict]
        | None
    ) = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[FFmpegOptionDict],
) -> bytes | None:
    """Transcode media files to another format/encoding

    :param inputs: url/path of the input media file or a sequence of tuples, each
                   containing an input url and its options dict
    :param outputs: url/path of the output media file or a sequence of tuples, each
                    containing an output url and its options dict
    :param progress: progress callback function, defaults to None
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :param two_pass: True to encode in 2-pass
    :param pass1_omits: list of output arguments to ignore in pass 1, defaults to
                        None (removes 'c:a' or 'acodec'). For multiple outputs,
                        specify use list of the list of arguments, matching the
                        length of outputs, for per-output omission.
    :param pass1_extras: list of additional output arguments to include in pass 1,
                         defaults to None (add 'an' if `pass1_omits` also None)
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :param **options: FFmpeg options. For output and global options, use FFmpeg
                        option names as is. For input options, append "_in" to the
                        option name. For example, r_in=2000 to force the input frame
                        rate to 2000 frames/s (see :doc:`options`).

                        If multiple inputs or outputs are specified, these input
                        or output options specified here are treated as common
                        options, and the url-specific duplicate options in the
                        ``inputs`` or ``outputs`` sequence will overwrite those
                        specified here.
    :returns: if any of the outputs is stdout, returns output bytes

    """

    if utils.is_valid_input_url(inputs):
        inputs = [inputs]
    if utils.is_valid_output_url(outputs):
        outputs = [outputs]

    args, input_info, output_info = configure.init_media_transcoder(
        inputs, outputs, None, None, options
    )

    # check number of pipes
    nb_inpipes = sum(info["src_type"] == "buffer" for info in input_info)
    nb_outpipes = sum(info["dst_type"] == "buffer" for info in output_info)

    # if 0 or 1 buffered input and 0 or 1 buffered output, just use stdin/stdout
    simple_mode = nb_inpipes < 2 and nb_outpipes < 2

    if not simple_mode:
        raise NotImplementedError(
            "transcoding with multiple input or output pipes is not yet implemented."
        )

    # convert basic VF options to vf option
    for i in range(len(output_info)):
        configure.build_basic_vf(args, None, i)

    stdin, stdout, input = configure.assign_std_pipes(
        args, input_info, output_info, use_sp_run=True
    )

    kwargs = {**sp_kwargs} if sp_kwargs else {}
    kwargs.update(
        {
            "progress": progress,
            "overwrite": overwrite,
            "stdin": stdin,
            "stdout": stdout,
            "input": input,
            "capture_log": None if show_log else True,
        }
    )
    if two_pass:
        kwargs["pass1_omits"] = pass1_omits
        kwargs["pass1_extras"] = pass1_extras

    pout = (fp.run_two_pass if two_pass else fp.run)(args, **kwargs)
    if pout.returncode:
        raise FFmpegError(pout.stderr, show_log)

    if check_version("6.1", ">=") and show_log is None:
        e = FFmpegError(pout.stderr, show_log)
        if e.ffmpeg_msg:
            raise e

    if any(out[0] == "-" or out[0] == "pipe" or out[0] == "pipe:1" for out in outputs):
        return pout.stdout
