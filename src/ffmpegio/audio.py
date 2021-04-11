import sys
import numpy as np
from . import ffmpeg, probe


def _get_format(fmt):
    """get audio format

    :param fmt: ffmpeg sample_fmt or numpy dtype class
    :type fmt: str or numpy dtype class
    :return: tuple of pcm codec name and (dtype if sample_fmt given or sample_fmt if dtype given)
    :rtype: tuple
    """
    formats = dict(
        u8p=("pcm_u8", np.uint8),
        s16p=("pcm_s16le", np.int16),
        s32p=("pcm_s32le", np.int32),
        s64p=("pcm_s64le", np.int64),
        fltp=("pcm_f32le", np.float32),
        dblp=("pcm_f64le", np.float64),
        u8=("pcm_u8", np.uint8),
        s16=("pcm_s16le", np.int16),
        s32=("pcm_s32le", np.int32),
        s64=("pcm_s64le", np.int64),
        flt=("pcm_f32le", np.float32),
        dbl=("pcm_f64le", np.float64),
    )

    # byteorder = "be" if sys.byteorder == "big" else "le"

    return (
        formats.get(fmt, formats["s16"])
        if isinstance(fmt, str)
        else next(((v[0], k) for k, v in formats.items() if v[1] == fmt))
    )


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

    acodec, dtype = _get_format(info["sample_fmt"])

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
    acodec, _ = _get_format(data.dtype)
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
