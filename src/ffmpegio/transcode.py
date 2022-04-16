from collections.abc import Sequence
from . import ffmpegprocess, configure, utils, FFmpegError

__all__ = ["transcode"]


def transcode(
    inputs,
    outputs,
    progress=None,
    overwrite=None,
    show_log=None,
    two_pass=False,
    pass1_omits=None,
    pass1_extras=None,
    **options
):
    """Transcode media files to another format/encoding

    :param inputs: url/path of the input media file or a sequence of tuples, each
                   containing an input url and its options dict
    :type inputs: str or sequence of (str,dict)
    :param outputs: url/path of the output media file or a sequence of tuples, each
                    containing an output url and its options dict
    :type outputs: str or sequence of (str, dict)
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param two_pass: True to encode in 2-pass
    :param pass1_omits: list of output arguments to ignore in pass 1, defaults to
                        None (removes 'c:a' or 'acodec')
    :type pass1_omits: seq(str), optional
    :param pass1_extras: list of additional output arguments to include in pass 1,
                         defaults to None (add 'an' if `pass1_omits` also None)
    :type pass1_extras: dict(int:dict(str)), optional
    :param \\**options: FFmpeg options. For output and global options, use FFmpeg
                        option names as is. For input options, prepend "input\_" to
                        the option name. For example, input_r=2000 to force the
                        input frame rate to 2000 frames/s (see :doc:`options`).

                        If multiple inputs or outputs are specified, these input
                        or output options specified here are treated as common
                        options, and the url-specific duplicate options in the
                        ``inputs`` or ``outputs`` sequence will overwrite those
                        specified here.
    :type \\**options: dict, optional
    :return: returncode of FFmpeg subprocess
    :rtype: int


    """

    # split input and global options from options
    input_options = utils.pop_extra_options(options, "_in")
    global_options = utils.pop_global_options(options)

    # detect single input/output argument
    if isinstance(inputs, str) or not isinstance(inputs, Sequence):
        inputs = [(inputs, None)]
    if isinstance(outputs, str) or not isinstance(outputs, Sequence):
        outputs = [(outputs, None)]

    # initialize FFmpeg argument dict
    args = configure.empty(global_options)

    for url, opts in inputs:
        opts = {**input_options, **(opts or {})}
        input_url, stdin, input = configure.check_url(url, False, opts.get("f", None))
        configure.add_url(args, "input", input_url, opts)

    for url, opts in outputs:
        opts = {**options, **(opts or {})}
        output_url, stdout, _ = configure.check_url(url, True)
        i, _ = configure.add_url(args, "output", output_url, opts)

        # convert basic VF options to vf option
        configure.build_basic_vf(args, None, i)

    kwargs = (
        {
            "pass1_omits": None if pass1_omits is None else [pass1_omits],
            "pass1_extras": None if pass1_extras is None else [pass1_extras],
        }
        if two_pass
        else {}
    )

    pout = (ffmpegprocess.run_two_pass if two_pass else ffmpegprocess.run)(
        args,
        progress=progress,
        overwrite=overwrite,
        capture_log=None if show_log else True,
        stdin=stdin,
        stdout=stdout,
        input=input,
        **kwargs,
    )
    if pout.returncode:
        raise FFmpegError(pout.stderr, show_log)
