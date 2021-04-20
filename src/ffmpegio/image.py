import numpy as np
from . import ffmpeg, utils, configure


def read(input_url, stream_id=0, **options):
    """read image/video frame snapshot

    :param filename: image/video file
    :type filename: str
    :param time: time marker to take a snapshot if `filename` is a video, defaults to None or to take
                 snapshot at time 0.0.
    :type time: float, optional
    :param pix_fmt: returning pixel format, defaults to None
    :type pix_fmt: str, optional
    :param background_color: background color if alpha channel is removed, defaults to "white"
    :type background_color: str, optional
    :return: image data
    :rtype: numpy.ndarray
    """

    args = configure.input_timing(
        input_url,
        vstream_id=stream_id,
        aliases={"time": "start"},
        excludes=("start", "end", "duration"),
        **options
    )

    configure.audio_codec("-", args, codec="none")

    args, reader_cfg = configure.video_io(
        input_url,
        stream_id,
        output_url="-",
        format="rawvideo",
        ffmpeg_args=args,
        excludes=["frame_rate"],
        **options
    )
    dtype, shape, _ = reader_cfg[0]

    configure.merge_user_options(args, "output", {"frames:v": 1}, file_index=0)
    stdout = ffmpeg.run_sync(args)
    return np.frombuffer(stdout, dtype=dtype).reshape(shape)


def write(url, data, **options):

    args = configure.input_timing(
        "-", vstream_id=0, excludes=("start", "end", "duration"), **options
    )

    configure.video_io(
        utils.array_to_video_input(data, format="rawvideo"),
        output_url=url,
        ffmpeg_args=args,
        excludes=["frame_rate"],
        **options
    )
    configure.merge_user_options(args, "output", {"frames:v": 1}, file_index=0)

    ffmpeg.run_sync(args, input=data.tobytes())
