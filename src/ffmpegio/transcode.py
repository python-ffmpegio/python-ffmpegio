from . import ffmpegprocess, configure, utils
from .utils.log import FFmpegError


def transcode(
    input_url,
    output_url,
    progress=None,
    overwrite=None,
    show_log=None,
    two_pass=False,
    pass1_omits=None,
    pass1_extras=None,
    **options
):
    """Transcode a media file to another format/encoding

    :param input_url: url/path of the input media file
    :type input_url: str
    :param output_url: url/path of the output media file
    :type output_url: str
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
                        option names as is. For input options, prepend "input_" to
                        the option name. For example, input_r=2000 to force the
                        input frame rate to 2000 frames/s (see :doc:`options`).
    :type \\**options: dict, optional
    :return: returncode of FFmpeg subprocess
    :rtype: int


    """

    input_url, stdin, input = configure.check_url(input_url, False)
    output_url, stdout, _ = configure.check_url(output_url, True)

    input_options = utils.pop_extra_options(options, "_in")

    args = configure.empty()
    configure.add_url(args, "input", input_url, input_options)[1][1]
    configure.add_url(args, "output", output_url, options)

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
        capture_log=False if show_log else True,
        stdin=stdin,
        stdout=stdout,
        input=input,
        **kwargs,
    )
    if pout.returncode:
        raise FFmpegError(pout.stderr, show_log)
