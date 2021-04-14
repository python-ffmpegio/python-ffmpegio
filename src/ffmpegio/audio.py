import sys
import numpy as np
from . import ffmpeg, probe, utils




def read(filename, **inopts):
    """Open an audio file.

    :param filename: Input media file.
    :type filename: str
    :raises Exception: if FFmpeg fails
    :return: sample rate and audio data matrix (column=time,row=channel)
    :rtype: (float, numpy.ndarray)
    """
    info = probe.audio_streams_basic(
        filename, index=0, entries=("sample_rate", "sample_fmt", "channels")
    )[0]

    acodec, dtype = utils.get_audio_format(info["sample_fmt"])

    args = dict(
        inputs=[(filename, None,)],
        outputs=[("-", dict(vn=None, acodec=acodec, f="rawvideo", map="a:0"))],
    )

    stdout = ffmpeg.run_sync(args)
    return (
        info["sample_rate"],
        np.frombuffer(stdout, dtype=dtype).reshape(-1, info["channels"]),
    )


def write(filename, rate, data, **outopts):
    """Write a NumPy array as an audio file.

    :param filename: Output media file.
    :type filename: str
    :param rate: The sample rate (in samples/sec).
    :type rate: int
    :param data: A 1-D or 2-D NumPy array of either integer or float data-type.
    :type data: numpy.ndarray
    :raises Exception: FFmpeg error
    """
    acodec, _ = utils.get_audio_format(data.dtype)
    args = dict(
        inputs=[
            (
                "-",
                dict(
                    vn=None,
                    f=acodec[4:],
                    ar=rate,
                    channels=data.shape[1] if data.ndim > 1 else 1,
                ),
            )
        ],
        outputs=[(filename, None,)],
    )

    ffmpeg.run_sync(args, input=data.tobytes())
