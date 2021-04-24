import numpy as np
from . import ffmpeg, utils, configure


def read(url, stream_id=0, **options):
    """Read an image file or a snapshot of a video frame

    :param url: URL of the image or video file to read.
    :type url: str
    :param stream_id: video stream id (numeric part of ``v:#`` specifier), defaults to 0.
    :type stream_id: int, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    :return: image data
    :rtype: numpy.ndarray

    Note on \\**options: To specify the video frame capture time, use `time`
    option which is an alias of `start` standard option.
    """

    args = configure.input_timing(
        url,
        vstream_id=stream_id,
        aliases={"time": "start"},
        excludes=("start", "end", "duration"),
        **options
    )

    configure.codec("-", "a", ffmpeg_args=args, codec="none")

    args, reader_cfg = configure.video_io(
        url,
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
    """Write a NumPy array to an image file.

    :param url: URL of the image file to write.
    :type url: str
    :param data: image data 3-D array (rowsxcolsxcomponents)
    :type data: `numpy.ndarray`
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    """
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
