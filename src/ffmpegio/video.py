import numpy as np
from . import ffmpeg, utils, probe


def read(filename, vframes, start_time=None, **kwargs):
    """read video frames

    :param filename: audio/video filename
    :type filename: str
    :param vframes: number of frames to read
    :type vframes: [type]
    :raises Exception: if FFmpeg fails
    :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
    :rtype: (fractions.Fraction, numpy.ndarray)
    """

    inputs, outputs, global_options, dtype, shape = utils.config_image_reader(
        filename, **kwargs
    )
    if vframes > 0:
        outputs[0][1]["vframes"] = vframes
    if start_time is not None:
        inputs[0][1]["ss"] = start_time
    fs = probe.video_streams_basic(filename, 0, ("frame_rate",))[0]["frame_rate"]
    args = dict(global_options=global_options, inputs=inputs, outputs=outputs)
    stdout = ffmpeg.run_sync(args)
    return fs, np.frombuffer(stdout, dtype=dtype).reshape((-1, *shape))


def write(filename, rate, data, **options):
    inputs, outputs = utils.config_image_writer(
        filename, data.dtype, data.shape[1:], **options
    )
    inputs[0][1]["r"] = rate
    args = dict(inputs=inputs, outputs=outputs)
    ffmpeg.run_sync(args, input=data.tobytes())
