"""Audio Read/Write Module
"""
import numpy as np
from . import ffmpeg, utils, configure, filter_utils


def create(name, *args, **kwargs):
    """Create audio data using an audio source filter

    :param name: name of the source filter
    :type name: str
    :param \\*args: filter arguments
    :type \\*args: tuple, optional
    :param \\**options: filter keyword arguments
    :type \\**options: dict, optional
    :return: video data
    :rtype: numpy.ndarray

    .. note:: Either `duration` or `nb_samples` filter options must be set.

    Supported Audio Source Filters
    ------------------------------

    =============  ==============================================================================
    filter name    description
    =============  ==============================================================================
    "aevalsrc"     an audio signal specified by an expression
    "flite"        synthesize a voice utterance
    "anoisesrc"    a noise audio signal
    "sine"         audio signal made of a sine wave with amplitude 1/8
    =============  ==============================================================================

    https://ffmpeg.org/ffmpeg-filters.html#Video-Sources

    """

    # if duration is not None:
    #     nb_samples = int(duration * sample_rate)
    # elif nb_samples is not None:
    #     duration = nb_samples / sample_rate
    # else:
    #     raise Exception("either duration or nb_samples must be specified")

    url = filter_utils.compose_filter(name, *args, **kwargs)

    nb_samples = filter_utils.analyze_filter(url, ("nb_samples",))["nb_samples"]
    if nb_samples is None:
        raise Exception("Filter must define either 'nb_samples' or 'duration'")

    ffmpeg_args = configure.empty()
    configure.add_url(ffmpeg_args, "input", url, {"f": "lavfi"})

    args, reader_cfg = configure.audio_io(
        ffmpeg_args, url, 0, output_url="-", format="rawvideo"
    )

    dtype, nch, rate = reader_cfg[0]

    configure.merge_user_options(
        ffmpeg_args, "output", {"t": nb_samples / rate}, file_index=0
    )

    stdout = ffmpeg.run_sync(ffmpeg_args)
    return np.frombuffer(stdout, dtype=dtype).reshape(-1, nch)


def read(url, stream_id=0, **options):
    """Read audio samples.

    :param url: URL of the audio file to read.
    :type url: str
    :param stream_id: audio stream id (the numeric part of ``a:#`` specifier), defaults to 0.
    :type stream_id: int, optional
    :param \\**options: other keyword options (see :doc:`options`)
    :type \\**options: dict, optional
    :return: sample rate in samples/second and audio data matrix (timexchannel)
    :rtype: tuple(`float`, :py:class:`numpy.ndarray`)

    .. note:: Even if :code:`start_time` option is set, all the prior samples will be read. 
        The retrieved data will be truncated before returning it to the caller.
        This is to ensure the timing accuracy. As such, do not use this function
        to perform block-wise processing. Instead use the streaming solution,
        see :py:func:`open`.


    """

    args = configure.input_timing({}, url, astream_id=stream_id, **options)

    i0, i1 = configure.get_audio_range(args, 0, stream_id)
    if i0 > 0:
        # if start time is set, remove to read all samples from the beginning
        del args["inputs"][0][1]["ss"]

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

    ffmpeg.run_sync(args, input=np.asarray(data).tobytes())
