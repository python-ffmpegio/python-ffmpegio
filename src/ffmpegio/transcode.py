from os import path

from . import ffmpeg, configure


def transcode(
    input_url,
    output_url,
    input_options=None,
    output_options=None,
    global_options=None,
    **options
):
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
    :param \\**options: other keyword options (see :doc:`options`).
    :type \\**options: dict, optional
    :return: returncode of FFmpeg subprocess
    :rtype: int


    """

    args = configure.input_timing(input_url, **options)

    configure.video_codec(output_url, args, prefix="video_", **options)
    configure.audio_codec(output_url, args, prefix="audio_", **options)
    configure.filters(output_url, args, **options)

    configure.video_io(
        input_url,
        0,
        output_url=output_url,
        format=None,
        ffmpeg_args=args,
        prefix="video_",
        **options,
    )

    configure.audio_io(
        input_url,
        0,
        output_url=output_url,
        ffmpeg_args=args,
        prefix="audio_",
        **options,
    )

    configure.global_options(ffmpeg_args=args, **options)

    if input_options:
        configure.merge_user_options(args, "input", input_options)

    if output_options:
        configure.merge_user_options(args, "output", input_options)

    if global_options:
        configure.merge_user_options(args, "global", input_options)

    # TODO run async and monitor stderr for better error handling
    try:
        ffmpeg.run_sync(args, stdout=None, stderr=None)
    except Exception as e:
        if configure.is_forced(args) and path.isfile(output_url):
            raise e
