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
    """Transcode a media file/stream to another format

    https://ffmpeg.org/ffmpeg.html

    :param input_url: url/path of the input media file
    :type input_url: str
    :param output_url: url/path of the output media file
    :type output_url: str
    :param start: start time in seconds or in the units as specified by `units` parameter, defaults to None, or from the beginning of the input
    :type start: numeric, optional
    :param end: end time in seconds or in the units as specified by `units` parameter, defaults to None, or to the end of the input
    :type end: numeric, optional
    :param duration: output duration in seconds or in the units as specified by `units` parameter, defaults to None, or the duration from `start` to the end of the input file
    :type duration: numeric, optional
    :param units: units of `start`, `end`, and `duration` parameters: "seconds", "frames", and "samples". defaults to "seconds".
    :type units: str, optional
    :param input_frame_rate: force input frame rate, defaults to None
    :type input_frame_rate: numeric, `fractions.Fraction`, or str, optional
    :param audio_codec: name of audio codec, "none", or "copy", defaults to None (auto-detect). Run `caps.coders('encoders','audio')` to get the list of available audio encoders
    :type audio_codec: str, optional
    :param audio_channels: number of audio channels, defaults to None (same as input)
    :type audio_channels: int, optional
    :param audio_sample_fmt: audio sample format, defaults to None (same as input). Run `caps.samplefmts()` to list available formats and their bits/sample.
    :type audio_sample_fmt: str, optional
    :param audio_filter: filtergraph definition to filter the audio stream, defaults to None
    :type audio_filter: str, optional
    :param video_codec: name of video codec, "none", or "copy", defaults to None (auto-detect). Run `caps.coders('encoders','video')` to get the list of available video encoders
    :type video_codec: str, optional
    :param video_crf: constant quality, defaults to None
    :type video_crf: int, optional
    :param video_pix_fmt: pixel format, defaults to None. Run `caps.pixfmts()` to list all available pixel formats.
    :type video_pix_fmt: str, optional
    :param video_filter: filtergraph definition for filtering video streams, defaults to None
    :type video_filter: str, optional
    :param input_options: dict of user-defined input options, defaults to None. each key is FFmpeg option argument without leading '-' with trailing stream specifier if needed. For flag options, set their values to None.
    :param force: True to overwrite if file exists or False to skip. If None or
                  unspecified, FFmpeg will ask for resolution.
    :type input_options: dict, optional
    :param output_options: dict of user-defined output options, defaults to None. each key is FFmpeg option argument without leading '-' with trailing stream specifier if needed. For flag options, set their values to None.
    :type output_options: dict, optional
    :param global_options: dict of user-defined global options, defaults to None. each key is FFmpeg option argument without leading '-' with trailing stream specifier if needed. For flag options, set their values to None.
    :type global_options: dict, optional
    :return: returncode of FFmpeg subprocess
    :rtype: int

    notes:

    `start` vs `end` vs `duration` - Only 2 out of 3 are honored.

        =======  =====  ==========  ======================================================================
        `start`  `end`  `duration`  FFmpeg config
        =======  =====  ==========  ======================================================================
           X                        start time specified, transcode till the end of input
                   X                transcode from the beginning of the input till `end` time is hit
                            X       transcode from the beginning of the input till encoded `duration` long
           X       X                start and end time specified
           X                X       start and duration specified
                   X        X       end and duration nspecified (start = end - duration)
           X       X        X       `end` parameter ignored
        =======  =====  ==========  ======================================================================


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
