from os import path

from . import ffmpegprocess, configure


def transcode(input_url, output_url, progress=None, capture_log=None, **options):
    """Transcode a media file to another format/encoding

    :param input_url: url/path of the input media file
    :type input_url: str
    :param output_url: url/path of the output media file
    :type output_url: str
    :param input_options: user_defined input options, defaults to None. each key is FFmpeg option argument without leading '-' with trailing stream specifier if needed. For flag options, set their values to None
    :type input_options: dict, optional
    :param output_options: dict of user-defined output options, defaults to None. each key is FFmpeg option argument without leading '-' with trailing stream specifier if needed. For flag options, set their values to None.
    :type output_options: dict, optional
    :param global_options: dict of user-defined global options, defaults to None. each key is FFmpeg option argument without leading '-' with trailing stream specifier if needed. For flag options, set their values to None.
    :type global_options: dict, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param capture_log: True to capture log messages on stderr, False to send
                    logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param \\**options: other keyword options (see :doc:`options`).
    :type \\**options: dict, optional
    :return: returncode of FFmpeg subprocess
    :rtype: int


    """

    input_url, stdin, input = configure.check_url(input_url, False)
    output_url, stdout, _ = configure.check_url(output_url, True)

    if input is not None:
        input_url = "-"

    args = configure.input_timing({}, input_url, **options)

    configure.codec(args, output_url, "v", prefix="video_", **options)
    configure.codec(args, output_url, "a", prefix="audio_", **options)
    configure.filters(args, output_url, **options)

    configure.video_io(
        args,
        input_url,
        0,
        output_url=output_url,
        format=None,
        prefix="video_",
        **options,
    )

    configure.audio_io(
        args,
        input_url,
        0,
        output_url=output_url,
        prefix="audio_",
        **options,
    )

    configure.global_options(args, **options)

    if "input_options" in options:
        configure.merge_user_options(args, "input", options["input_options"])

    if "output_options" in options:
        configure.merge_user_options(args, "output", options["output_options"])

    if "global_options" in options:
        configure.merge_user_options(args, "global", options["global_options"])

    # TODO run async and monitor stderr for better error handling
    try:
        ffmpegprocess.run(
            args,
            progress=progress,
            capture_log=capture_log,
            stdin=stdin,
            stdout=stdout,
            input=input,
        )
    except Exception as e:
        if configure.is_forced(args) and path.isfile(output_url):
            raise e
