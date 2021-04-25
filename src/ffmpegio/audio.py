"""Audio Read/Write Module
"""
import numpy as np
from . import ffmpeg, utils, configure


def read(url, stream_id=0, **options):
    """Read audio samples.

    :param url: URL of the audio file to read.
    :type url: str
    :param stream_id: audio stream id (the numeric part of ``a:#`` specifier), defaults to 0.
    :type stream_id: int, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    :return: sample rate in samples/second and audio data matrix (timexchannel)
    :rtype: tuple(`float`, `numpy.ndarray`)
    """

    args = configure.input_timing({}, url, astream_id=stream_id, **options)

    args, reader_cfg = configure.audio_io(
        args,
        url,
        stream_id,
        output_url="-",
        format="rawvideo",
        **options,
    )

    dtype, nch, rate = reader_cfg[0]
    stdout = ffmpeg.run_sync(args)
    return rate, np.frombuffer(stdout, dtype=dtype).reshape(-1, nch)


def write(url, rate, data, **options):
    """Write a NumPy array to an audio file.

    :param url: URL of the audio file to write.
    :type url: str
    :param rate: The sample rate in samples/second.
    :type rate: int
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    :param data: A 1-D or 2-D NumPy array of either integer or float data-type.
    :type data: `numpy.ndarray`
    """
    args = configure.input_timing(
        {},
        "-",
        astream_id=0,
        excludes=("start", "end", "duration"),
        **{"input_sample_rate": rate, **options},
    )

    configure.audio_io(
        args,
        utils.array_to_audio_input(rate, data=data, format=True),
        output_url=url,
        **options,
    )

    print(args)

    ffmpeg.run_sync(args, input=data.tobytes())
