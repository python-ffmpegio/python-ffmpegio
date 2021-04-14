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
        data = self.stdout.read(nbytes if nbytes > 0 else -1)
        self.eof = nbytes < 1 or len(data) < nbytes
        return np.frombuffer(data, dtype=self.dtype).reshape((-1, *self.shape))

    def close(self):
        if not self.eof:
            self.proc.terminate()
        self.proc.wait()


class SimpleVideoWriter:
    def __init__(self, url, rate, **kwargs) -> None:
        self.proc = self.shape = None
        self.url = url
        self.frame_rate = rate
        self.options = kwargs
        self.frames_written = 0

    def write(self, data):
        """write video frames

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """

        if self.proc is not None:
            if data.dtype != self.dtype:
                raise Exception(
                    f"mismatched dtype. Expects {self.dtype} and received {data.dtype}"
                )

            shape = data.shape[-3:]
            if any([shape[i] != self.shape[i] for i in range(-1, -4, -1)]):
                raise Exception("mismatched frame size.")

        else:
            if data.ndim != 3 and data.ndim != 4:
                raise Exception("audio data must be 3d or 4d numpy.ndarray")

            inputs, outputs = utils.config_image_writer(
                self.url, data.dtype, data.shape[-3:], **self.options
            )
            inputs[0][1]["r"] = self.frame_rate
            args = dict(inputs=inputs, outputs=outputs)
            self.proc = ffmpeg.run(args, stdout=None, stdin=ffmpeg.PIPE)
            self.dtype = data.dtype
            self.shape = data.shape[-3:]

        self.proc.stdin.write(data.tobytes())
        self.frames_written += data.shape[0] if data.ndim == 4 else 1

    def close(self):
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait()


class SimpleAudioReader:
    def __init__(self, url, start_time=None, **kwargs) -> None:
        info = probe.audio_streams_basic(
            url, index=0, entries=("sample_rate", "sample_fmt", "channels")
        )[0]

        acodec, self.dtype = utils.get_audio_format(info["sample_fmt"])
        self.channels = info["channels"]
        self.sample_rate = info["sample_rate"]

        args = dict(
            inputs=[(url, {})],
            outputs=[("-", dict(vn=None, acodec=acodec, f="rawvideo", map="a:0"))],
        )
        if start_time is not None:
            args["input"][0]["ss"] = start_time
        self.proc = ffmpeg.run(args)
        self.stdout = self.proc.stdout
        self.eof = False
        self.itemsize = np.dtype(self.dtype).itemsize
        self._nbytes = self.channels * self.itemsize

    def read(self, nsamples=0):
        """read audio samples

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """
        nbytes = self._nbytes * nsamples
        data = self.stdout.read(nbytes if nbytes > 0 else -1)
        self.eof = nbytes < 1 or len(data) < nbytes
        return np.frombuffer(data, dtype=self.dtype).reshape((-1, self.channels))

    def close(self):
        if not self.eof:
            self.proc.terminate()
        self.proc.wait()


class SimpleAudioWriter:
    def __init__(self, url, rate, **kwargs) -> None:
        self.proc = self.shape = None
        self.url = url
        self.sample_rate = rate
        self.options = kwargs
        self.samples_written = 0

    def write(self, data):
        """write audio data

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """

        if self.proc is not None:
            if data.dtype != self.dtype:
                raise Exception(
                    f"mismatched dtype. Expects {self.dtype} and received {data.dtype}"
                )
            if (data.ndim != 2 or self.channels != data.shape[-1]) and (
                data.ndim != 1 or self.channels != 1
            ):
                raise Exception("mismatched number of channels")

        else:
            if data.ndim != 2 and data.ndim != 1:
                raise Exception("audio data must be 1d or 2d numpy.ndarray")
            self.dtype = data.dtype
            self.channels = data.shape[1] if data.ndim > 1 else 1
            acodec, _ = utils.get_audio_format(data.dtype)
            args = dict(
                inputs=[
                    (
                        "-",
                        dict(
                            vn=None,
                            f=acodec[4:],
                            ar=self.sample_rate,
                            channels=self.channels,
                        ),
                    )
                ],
                outputs=[(self.url, None)],
            )
            self.proc = ffmpeg.run(args, stdout=None, stdin=ffmpeg.PIPE)

        self.proc.stdin.write(data.tobytes())
        self.samples_written += data.shape[0]

    def close(self):
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait()
