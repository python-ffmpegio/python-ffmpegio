import numpy as np
from . import ffmpeg, utils, configure


def read(url, vframes, stream_id=0, **options):
    """read video frames

    :param filename: audio/video filename
    :type filename: str
    :param vframes: number of frames to read
    :type vframes: [type]
    :raises Exception: if FFmpeg fails
    :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
    :rtype: (fractions.Fraction, numpy.ndarray)
    """

    args = configure.input_timing(url, vstream_id=stream_id, **options)

    args, reader_cfg = configure.video_io(
        url,
        stream_id,
        output_url="-",
        format="rawvideo",
        ffmpeg_args=args,
        excludes=["frame_rate"],
        **options
    )
    dtype, shape, rate = reader_cfg[0]

    configure.merge_user_options(args, "output", {"frames:v": vframes})
    stdout = ffmpeg.run_sync(args)
    return rate, np.frombuffer(stdout, dtype=dtype).reshape((-1, *shape))


def write(url, rate, data, **options):

    args = configure.input_timing(
        "-",
        vstream_id=0,
        excludes=("start", "end", "duration"),
        **{"input_frame_rate": rate, **options}
    )

    configure.video_io(
        utils.array_to_video_input(data, format="rawvideo"),
        output_url=url,
        ffmpeg_args=args,
        **options
    )

    ffmpeg.run_sync(args, input=data.tobytes())
