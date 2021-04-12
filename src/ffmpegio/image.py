import numpy as np
from . import ffmpeg, utils


def read(filename, time=None, **options):
    """read image/video frame snapshot

    :param filename: image/video file
    :type filename: str
    :param time: time marker to take a snapshot if `filename` is a video, defaults to None or to take
                 snapshot at time 0.0.
    :type time: float, optional
    :param pix_fmt: returning pixel format, defaults to None
    :type pix_fmt: str, optional
    :param background_color: background color if alpha channel is removed, defaults to "white"
    :type background_color: str, optional
    :return: image data
    :rtype: numpy.ndarray
    """

    inputs, outputs, global_options, dtype, shape = utils.config_image_reader(
        filename, 0, **options
    )
    outputs[0][1]["vframes"] = 1
    if time is not None:
        inputs[0][1]["ss"] = time
    args = dict(global_options=global_options, inputs=inputs, outputs=outputs)
    stdout = ffmpeg.run_sync(args)
    return np.frombuffer(stdout, dtype=dtype).reshape(shape)


def write(filename, data, **options):
    inputs, outputs = utils.config_image_writer(
        filename, data.dtype, data.shape, **options
    )
    args = dict(inputs=inputs, outputs=outputs)
    ffmpeg.run_sync(args, input=data.tobytes())
