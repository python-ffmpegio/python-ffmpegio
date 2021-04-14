import numpy as np
from . import ffmpeg, utils, configure


def read(input_url, stream_id=0, **options):
    """Open an audio file.

    :param filename: Input media file.
    :type filename: str
    :raises Exception: if FFmpeg fails
    :return: sample rate and audio data matrix (column=time,row=channel)
    :rtype: (float, numpy.ndarray)
    """

    args = configure.input_timing(input_url, astream_id=stream_id, **options)

    args, reader_cfg = configure.audio_io(
        input_url,
        stream_id,
        output_url="-",
        format="rawvideo",
        ffmpeg_args=args,
        **options,
    )

    dtype, nch, rate = reader_cfg[0]
    stdout = ffmpeg.run_sync(args)
    return rate, np.frombuffer(stdout, dtype=dtype).reshape(-1, nch)


def write(url, rate, data, **options):
    """Write a NumPy array as an audio file.

    :param url: Output media file.
    :type url: str
    :param rate: The sample rate (in samples/sec).
    :type rate: int
    :param data: A 1-D or 2-D NumPy array of either integer or float data-type.
    :type data: numpy.ndarray
    :raises Exception: FFmpeg error
    """
    args = configure.input_timing(
        "-",
        astream_id=0,
        excludes=("start", "end", "duration"),
        **{"input_sample_rate": rate, **options},
    )

    configure.audio_io(
        utils.array_to_audio_input(data, format=True),
        output_url=url,
        ffmpeg_args=args,
        **options,
    )

    ffmpeg.run_sync(args, input=data.tobytes())
