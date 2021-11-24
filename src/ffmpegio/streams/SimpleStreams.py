import logging
import numpy as np
from .. import utils, configure, ffmpegprocess, io


class SimpleVideoReader:
    def __init__(
        self,
        url,
        stream_id=0,
        progress=None,
        capture_log=None,
        queue_size=None,
        **options,
    ) -> None:
        self.url = url
        self.stream_id = stream_id

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

        # index of the next frame
        self.frame_index = int(
            (utils.parse_time_duration(configure.get_option(args, "input", "ss")) or 0)
            * self.frame_rate
        )

        self._proc = ffmpegprocess.Popen(
            args,
            progress=progress,
            capture_log=capture_log,
            input_queue_size=queue_size or 16,
        )

    def read(self, vframes=1, block=True, timeout=None):
        """read video frames

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """

        return self._proc.stdout.read_as_array(
            vframes, block, timeout, self.shape, self.dtype
        )

    def close(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None


class SimpleVideoWriter:
    def __init__(
        self,
        url,
        rate,
        pix_fmt=None,
        size=None,
        progress=None,
        input_copy=True,
        capture_log=None,
        queue_size=None,
        **kwargs,
    ) -> None:
        self.url = url
        self.frame_rate = rate
        self.size = size  # (w,h)
        self.options = kwargs
        self.frames_written = 0
        self.progress = progress
        self.input_copy = input_copy
        self.capture_log = capture_log
        self.queue_size = queue_size

        if pix_fmt is None or size is None:
            if pix_fmt is not None or size is not None:
                logging.warn(
                    "Video stream not opened at the time of instantiation: only pix_fmt or size provided"
                )
            self._proc = self.shape = self.dtype = None
        else:
            self._open(pix_fmt=pix_fmt, size=size)

    def _open(self, data=None, pix_fmt=None, size=None):
        args = configure.input_timing(
            {},
            "-",
            vstream_id=0,
            excludes=("start", "end", "duration"),
            **{"input_frame_rate": self.frame_rate, **self.options},
        )

        input, self.shape, self.dtype = utils.array_to_video_input(
            self.frame_rate, data, format="rawvideo", pix_fmt=pix_fmt, size=size
        )

        configure.video_io(
            args,
            input,
            output_url=self.url,
            **self.options,
        )

        self._proc = ffmpegprocess.Popen(
            args,
            progress=self.progress,
            input_copy=self.input_copy,
            capture_log=self.capture_log,
            input_queue_size=self.queue_size or 16,
        )

    def write(self, data, block=True, timeout=None):
        """write video frames

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """

        data = np.asarray(data)

        if self._proc is not None:
            if data.dtype != self.dtype:
                raise Exception(
                    f"mismatched dtype. Expects {self.dtype} and received {data.dtype}"
                )

            shape = data.shape[-3:]
            if any([shape[i] != self.shape[i] for i in range(-1, -4, -1)]):
                raise Exception("mismatched frame size.")

        else:
            self._open(data)
        self._proc.stdin.write(data, block, timeout)
        self.frames_written += data.shape[0] if data.ndim == 4 else 1

    def close(self, timeout=0.1):
        if self._proc:
            self._proc.stdin.mark_eof()
            self._proc.stdin.close(timeout, True)
            if self._proc.wait(timeout) is None:
                self._proc.terminate()
            self._proc = None


class SimpleAudioReader:
    def __init__(
        self,
        url,
        stream_id=0,
        progress=None,
        capture_log=None,
        queue_size=None,
        **options,
    ) -> None:
        self.url = url
        self.stream_id = stream_id
        args = configure.input_timing({}, url, astream_id=stream_id, **options)

        start, end = configure.adjust_audio_range(args, 0, stream_id)

        args, reader_cfg = configure.audio_io(
            args,
            url,
            int(stream_id),
            output_url="-",
            format="rawvideo",
            **options,
        )

        self.dtype, self.channels, self.sample_rate = reader_cfg[0]

        self._proc = ffmpegprocess.Popen(
            args,
            progress=progress,
            capture_log=capture_log,
            output_queue_size=queue_size or 16,
        )

        self.remaining = end
        self.sample_index = start

        # if starting mid-stream, drop earlier samples
        if start > 0:
            nblk = self.channels * np.dtype(self.dtype).itemsize
            self.remaining -= len(self._proc.stdout.read(start * nblk, True)) // nblk

    def read(self, nsamples=0, block=True, timeout=None):
        """read audio samples

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """

        if not self.remaining:
            return None

        if nsamples > self.remaining:
            nsamples = self.remaining

        data = self._proc.stdout.read_as_array(
            nsamples, block, timeout, self.channels, self.dtype
        )
        self.remaining -= data.shape[0]
        self.sample_index += data.shape[0]

        return data

    def readiter(self, nsamples, block=True, timeout=None):
        while self.remaining > 0:
            try:
                data = self.read(nsamples, block, timeout)
                yield data
            except io.Empty:
                logging.debug('[SimpleAudioRear::readiter] read returned empty')
                break
        logging.debug(f"[SimpleAudioRear::readiter] stopped reading (remaining: {self.remaining} samples)")

    def close(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None


class SimpleAudioWriter:
    def __init__(
        self,
        url,
        rate,
        dtype=None,
        channels=None,
        progress=None,
        input_copy=True,
        capture_log=None,
        queue_size=None,
        **options,
    ) -> None:
        self._proc = None
        self.url = url
        self.samples_written = 0
        self.progress = progress
        self.input_copy = input_copy
        self.capture_log = capture_log
        if dtype is None or channels is None:
            self.sample_rate = rate
            self.dtype = dtype
            self.channels = channels
            self.options = options
        else:
            self.open(
                rate, dtype=dtype, channels=channels, queue_size=queue_size, **options
            )

    def open(
        self, rate, data=None, dtype=None, channels=None, queue_size=None, **options
    ):
        if self._proc:
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
        self._proc = ffmpegprocess.Popen(
            args,
            progress=self.progress,
            input_copy=self.input_copy,
            capture_log=self.capture_log,
            input_queue_size=queue_size or 16,
        )
        self.samples_written = 0

    def write(self, data, block=True, timeout=None):
        """write audio data

        :param url: audio/video url
        :type url: str
        :param vframes: number of frames to read
        :type vframes: [type]
        :raises Exception: if FFmpeg fails
        :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
        :rtype: (fractions.Fraction, numpy.ndarray)
        """

        data = np.asarray(data)

        if self._proc is not None:
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

        self._proc.stdin.write(data, block, timeout)
        self.samples_written += data.shape[0]

    def close(self, timeout=0.1):
        if self._proc:
            self._proc.stdin.mark_eof()
            self._proc.stdin.close(timeout, True)
            if self._proc.wait(timeout) is None:
                self._proc.terminate()
            self._proc = None
