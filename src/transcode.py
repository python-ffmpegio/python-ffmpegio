from . import ffmpeg
from . import probe


def transcode_sync(
    input_url,
    output_url,
    start=None,
    end=None,
    duration=None,
    units="seconds",
    input_frame_rate=None,
    audio_codec=None,
    audio_channels=None,
    audio_sample_fmt=None,
    audio_filter=None,
    video_codec=None,
    video_crf=None,
    video_pix_fmt=None,
    video_filter=None,
    input_options=None,
    output_options=None,
    global_options=None,
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
    inopts = {}

    # if start/end/duration are specified
    need_units = start or end or duration
    fs = (
        1.0
        if need_units or units == "seconds"
        else float(
            probe.video_streams_basic(input_url, index=0, entries=("frame_rate",))[0][
                "frame_rate"
            ]
        )
        if units == "frames"
        else probe.audio_streams_basic(input_url, index=0, entries=("sample_rate",))[0][
            "sample_rate"
        ]
    )

    if start:
        inopts["ss"] = float(start / fs)
    elif end and duration:
        inopts["ss"] = float((end - duration) / fs)
    if end:
        inopts["to"] = float(end / fs)
    if duration:
        inopts["t"] = float(duration / fs)

    if input_frame_rate is not None:
        inopts["r"] = input_frame_rate

    if input_options:
        inopts = {
            **inopts,
            **(
                ffmpeg.parse_options(input_options)
                if isinstance(input_options, str)
                else input_options
            ),
        }

    ################################

    outopts = {}

    if video_codec is not None:
        if video_codec == "none":
            outopts["vn"] = None
        else:
            outopts["vcodec"] = video_codec
    if video_crf is not None:
        outopts["crf"] = video_crf

    if video_pix_fmt is not None:
        outopts["pix_fmt"] = video_pix_fmt

    if audio_codec is not None:
        if audio_codec == "none":
            outopts["an"] = None
        else:
            outopts["acodec"] = audio_codec

    if audio_channels is not None:
        outopts["ac"] = audio_channels

    if audio_sample_fmt is not None:
        outopts["sample_fmt"] = audio_sample_fmt

    if audio_filter is not None:
        outopts["af"] = audio_filter

    if video_filter is not None:
        outopts["vf"] = video_filter

    if output_options:
        outopts = {
            **outopts,
            **(
                ffmpeg.parse_options(output_options)
                if isinstance(output_options, str)
                else output_options
            ),
        }

    if global_options and isinstance(global_options, str):
        global_options = ffmpeg.parse_options(global_options)

    args = dict(
        global_options=global_options,
        inputs=[(input_url, inopts)],
        outputs=[(output_url, outopts)],
    )

    ret = ffmpeg.run_sync(args, stdout=None, stderr=None,)

    return ret.returncode
