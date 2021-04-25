"""Audio Read/Write Module
"""
import numpy as np
from . import ffmpeg, utils, configure, streams


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

    .. note:: even if `start_time` option is set, prior samples are read, and
    the retrieved data matrix is truncated before returning it to the caller. 
    This is to ensure the timing accuracy. As such, do not use this function 
    to perform block-wise processing. Instead use the streaming solution, 
    see :py:func:`open`.

    """

    args = configure.input_timing({}, url, astream_id=stream_id, **options)

    i0, i1 = configure.get_audio_range(args, stream_id)
    if i0 > 0:
        # if start time is set, remove to read all samples from the beginning
        del args['inputs'][0][1]["ss"]

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

    data = np.frombuffer(stdout, dtype=dtype).reshape(-1, nch)
    return rate, data[i0:i1, ...]


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

    ffmpeg.run_sync(args, input=data.tobytes())
