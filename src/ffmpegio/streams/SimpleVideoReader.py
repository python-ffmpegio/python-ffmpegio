import numpy as np
from .. import ffmpeg, probe, utils


class SimpleVideoReader:
    def __init__(self, url, start_time=None, **kwargs) -> None:
        (
            inputs,
            outputs,
            global_options,
            self.dtype,
            self.shape,
        ) = utils.config_image_reader(url, **kwargs)
        if start_time is not None:
            inputs[0][1]["ss"] = start_time
        self.frame_rate = probe.video_streams_basic(url, 0, ("frame_rate",))[0][
            "frame_rate"
        ]
        args = dict(global_options=global_options, inputs=inputs, outputs=outputs)
        self.proc = ffmpeg.run(args)
        self.stdout = self.proc.stdout
        self.size = self.shape[0] * self.shape[1] * self.shape[2]
        self.itemsize = np.dtype(self.dtype).itemsize
        self._nbytes = self.size * self.itemsize
        self.eof = False

    def read(self, vframes=1):
        """read video frames

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """
        if self.eof:
            return None

        nbytes = self._nbytes * vframes
        data = self.stdout.read(nbytes)
        self.eof = len(data) < nbytes
        return np.frombuffer(data, dtype=self.dtype).reshape((-1, *self.shape))

    def close(self):
        if not self.eof:
            self.proc.terminate()
        self.proc.wait()
