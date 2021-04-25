import numpy as np
from .. import ffmpeg, probe, utils, configure


class SimpleVideoReader:
    def __init__(self, url, stream_id=0, **options) -> None:

        args = configure.input_timing({}, url, vstream_id=stream_id, **options)

        args, reader_cfg = configure.video_io(
            args,
            url,
            stream_id,
            output_url="-",
            format="rawvideo",
            excludes=["frame_rate"],
            **options,
        )

        self.dtype, self.shape, self.frame_rate = reader_cfg[0]

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
    def __init__(self, url, rate, dtype=None, shape=None, **kwargs) -> None:
        self.proc = self.shape = None
        self.url = url
        self.frame_rate = rate
        self.dtype = dtype
        self.shape = shape
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
            args = configure.input_timing(
                {},
                "-",
                vstream_id=0,
                excludes=("start", "end", "duration"),
                **{"input_frame_rate": self.frame_rate, **self.options},
            )

            configure.video_io(
                args,
                utils.array_to_video_input(self.frame_rate, data, format="rawvideo"),
                output_url=self.url,
                **self.options,
            )

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
    def __init__(self, url, stream_id=0, **options) -> None:
        args = configure.input_timing({}, url, astream_id=stream_id, **options)

        args, reader_cfg = configure.audio_io(
            args,
            url,
            int(stream_id),
            output_url="-",
            format="rawvideo",
            **options,
        )

        self.dtype, self.channels, self.sample_rate = reader_cfg[0]

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
    def __init__(self, url, rate, dtype=None, channels=None, **options) -> None:
        self.proc = None
        self.url = url
        self.samples_written = 0
        if dtype is None or channels is None:
            self.sample_rate = rate
            self.dtype = dtype
            self.channels = channels
            self.options = options
        else:
            self.open(rate, dtype=dtype, channels=channels, **options)

    def open(self, rate, data=None, dtype=None, channels=None, **options):
        if self.proc:
            raise Exception("stream is already open")

        if data is None:
            data = np.empty((1, channels), dtype=dtype)

        self.sample_rate = rate
        self.dtype = data.dtype
        self.channels = data.shape[1] if data.ndim > 1 else 1
        args = configure.input_timing(
            {},
            "-",
            astream_id=0,
            excludes=("start", "end", "duration"),
            **{"input_sample_rate": self.sample_rate, **self.options},
        )

        configure.audio_io(
            args,
            utils.array_to_audio_input(rate, data, format=True),
            output_url=self.url,
            **self.options,
        )
        self.proc = ffmpeg.run(args, stdout=None, stdin=ffmpeg.PIPE)
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
            self.open(self.sample_rate, data)

        self.proc.stdin.write(data.tobytes())
        self.samples_written += data.shape[0]

    def close(self):
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait()
