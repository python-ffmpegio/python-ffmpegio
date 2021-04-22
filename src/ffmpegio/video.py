import numpy as np
from . import ffmpeg, utils, configure


def read(url, vframes=None, stream_id=0, **options):
    """Read video frames

    :param url: URL of the video file to read.
    :type url: str
    :param vframes: number of frames to read, default to None. If not set,
                    uses the timing options to determine the number of frames.
    :type vframes: int, optional
    :param stream_id: video stream id (numeric part of ``v:#`` specifier), defaults to 0.
    :type stream_id: int, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional

    :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
    :rtype: (`fractions.Fraction`, `numpy.ndarray`)
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
    """Write Numpy array to a video file

    :param url: URL of the video file to write.
    :type url: str
    :param rate: frame rate in frames/second
    :type rate: `float`, `int`, or `fractions.Fraction`
    :param data: video frame data 4-D array (framexrowsxcolsxcomponents)
    :type data: `numpy.ndarray`
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    """
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
