from . import ffmpegprocess as fp, configure, utils, FFmpegError
from .path import check_version
from .errors import scan_stderr

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
    sp_kwargs=None,
    **options,
):
    """Transcode media files to another format/encoding

    :param inputs: url/path of the input media file or a sequence of tuples, each
                   containing an input url and its options dict
    :type inputs: str or a list of str or a sequence of (str,dict)
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
                        None (removes 'c:a' or 'acodec'). For multiple outputs,
                        specify use list of the list of arguments, matching the
                        length of outputs, for per-output omission.
    :type pass1_omits: seq(str), or seq(seq(str)) optional
    :param pass1_extras: list of additional output arguments to include in pass 1,
                         defaults to None (add 'an' if `pass1_omits` also None)
    :type pass1_extras: dict(int:dict(str)), optional
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                      `subprocess.Popen()` call used to run the FFmpeg, defaults
                      to None
    :type sp_kwargs: dict, optional
    :param \\**options: FFmpeg options. For output and global options, use FFmpeg
                        option names as is. For input options, append "_in" to the
                        option name. For example, r_in=2000 to force the input frame
                        rate to 2000 frames/s (see :doc:`options`).

                        If multiple inputs or outputs are specified, these input
                        or output options specified here are treated as common
                        options, and the url-specific duplicate options in the
                        ``inputs`` or ``outputs`` sequence will overwrite those
                        specified here.
    :type \\**options: dict, optional
    :returns: if any of the outputs is stdout, returns output bytes
    :rtype: bytes | None

    """

    # split input and global options from options
    input_options = utils.pop_extra_options(options, "_in")
    global_options = utils.pop_global_options(options)

    def format_arg(arg, defopts):
        def test(a, is_list):
            try:
                assert len(a) == 2
                assert isinstance(a[1], dict)
                return (a[0], {**defopts, **a[1]})
            except:
                if is_list:
                    return (a, defopts)
                raise

        # special case: a list of inputs w/out options
        if type(arg) == list:
            return [test(a, True) for a in arg]

        # attempt to map url-options pairs
        try:
            return [test(a, False) for a in arg]
        except:
            return [(arg, defopts)]

    inputs = format_arg(inputs, input_options)
    outputs = format_arg(outputs, options)

    # initialize FFmpeg argument dict
    args = configure.empty(global_options)

    for url, opts in inputs:
        input_url, stdin, input = configure.check_url(url, False, opts.get("f", None))
        configure.add_url(args, "input", input_url, opts)

    for url, opts in outputs:
        output_url, stdout, _ = configure.check_url(url, True)
        i, _ = configure.add_url(args, "output", output_url, opts)

        # convert basic VF options to vf option
        configure.build_basic_vf(args, None, i)

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
