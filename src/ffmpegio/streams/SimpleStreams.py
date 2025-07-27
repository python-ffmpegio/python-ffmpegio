"""SimpleStreams Module: FFmpeg"""

from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from ..plugins.hookspecs import FromBytesCallable, CountDataCallable, ToBytesCallable

from typing_extensions import Unpack
from collections.abc import Sequence
from .._typing import (
    DTypeString,
    ShapeTuple,
    ProgressCallable,
    RawDataBlob,
    FFmpegOptionDict,
    InputSourceDict,
    OutputDestinationDict,
)

from fractions import Fraction
from math import prod

from .. import configure, plugins
from ..stream_spec import stream_spec_to_map_option, StreamSpecDict
from ..errors import FFmpegioError
from ..configure import (
    FFmpegArgs,
    MediaType,
    FFmpegUrlType
)
from .BaseFFmpegRunner import BaseFFmpegRunner
from .._utils import get_bytesize

# fmt:off
__all__ = [ "SimpleVideoReader", "SimpleAudioReader", "SimpleVideoWriter",
    "SimpleAudioWriter"]
# fmt:on


class SimpleReaderBase(BaseFFmpegRunner):
    """base class for SISO media read stream classes"""

    def __init__(
        self,
        *,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict],
        from_bytes: FromBytesCallable,
        to_memoryview: ToBytesCallable,
        show_log: bool | None,
        progress: ProgressCallable | None,
        blocksize: int,
        default_timeout: float | None,
        sp_kwargs: dict | None,
    ):
        """Queue-less simple media io runner

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg input option dicts with zero or one streaming pipe. (only one in input or output)
        :param output_info: FFmpeg output option dicts with zero or one any streaming pipe. (only one in input or output)
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        super().__init__(
            ffmpeg_args=ffmpeg_args,
            input_info=input_info,
            output_info=output_info,
            input_ready=True,
            init_deferred_outputs=None,
            deferred_output_args=[],
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            sp_kwargs={**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
            blocksize=blocksize,
            ref_output=0,
        )

        self._converter = from_bytes
        self._memoryviewer = to_memoryview

        # set the default read block size for the reference stream
        self._blocksize = blocksize

        # set the default read block size for the referenc stream
        info = self._output_info[0]
        assert "raw_info" in info

        self._rate = info["raw_info"][2]
        self._n0 = 0  # timestamps of the last read sample

    @property
    def output_label(self) -> str | None:
        """FFmpeg/custom labels of output streams"""
        return self._output_info[0]["user_map"]

    @property
    def output_type(self) -> MediaType | None:
        """media type associated with the output streams (key)"""
        return self._output_info[0]["media_type"]

    @property
    def output_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][2] if "raw_info" in info else None

    @property
    def output_dtype(self) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][0] if "raw_info" in info else None

    @property
    def output_shape(self) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""
        info = self._output_info[0]
        return info["raw_info"][1] if "raw_info" in info else None

    @property
    def output_count(self) -> int:
        """number of frames/samples read"""
        return self._n0

    @property
    def output_bytesize(self) -> int|None:
        """number of bytes per output sample/pixel"""
        return get_bytesize(self.output_shape,self.output_dtype)

    def _assign_pipes(self):

        configure.assign_output_pipes(
            self._args["ffmpeg_args"],
            self._output_info,
            self._args["sp_kwargs"],
            use_std_pipes=True,
        )

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize, self.default_timeout)
        if F is None:
            raise StopIteration
        return F

    def read(
        self, n: int, squeeze: bool = False
    ) -> RawDataBlob:
        """Read and return numpy.ndarray with up to n frames/samples. If
        the argument is omitted, None, or negative, data is read and
        returned until EOF is reached. An empty bytes object is returned
        if the stream is already at EOF.

        If the argument is positive, and the underlying raw stream is not
        interactive, multiple raw reads may be issued to satisfy the byte
        count (unless EOF is reached first). But for interactive raw streams,
        at most one raw read will be issued, and a short result does not
        imply that EOF is imminent.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        info = self._output_info[0]
        converter = self._converter
        nbytes = self.output_bytesize
        assert nbytes is not None

        dtype, shape, _ = info["raw_info"] # type: ignore

        b = self._proc.stdout.read(n*nbytes) # type: ignore
        data = converter(b=b, dtype=dtype, shape=shape, squeeze=squeeze)

        # update the frame/sample counter
        n = len(b)//nbytes  # actual number read
        self._n0 += n

        return data

    def readinto(self, array: RawDataBlob) -> int:
        """Read bytes into a pre-allocated, writable bytes-like object array and
        return the number of bytes read. For example, b might be a bytearray.

        Like read(), multiple reads may be issued to the underlying raw stream,
        unless the latter is interactive.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        info = self._output_info[0]
        assert 'raw_info' in info
        shape = info["raw_info"][1]

        return self._proc.stdout.readinto(self._memoryviewer(obj=array)) // prod( # type: ignore
            shape[1:]
        ) 


class SimpleVideoReader(SimpleReaderBase):

    def __init__(
        self,
        url: FFmpegUrlType,
        *,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int = 1,
        sp_kwargs: dict | None = None,
        stream: str | StreamSpecDict | None = None,
        default_timeout: float | None = None,
        **options,
    ):
        # assign the input stream
        map = "0:V:0" if stream is None else stream_spec_to_map_option(stream)

        args, input_info, ready, output_info, _ = configure.init_media_read(
            [url], [map], options
        )

        if len(output_info) != 1 or output_info[0]["media_type"] != "video":
            raise FFmpegioError(f'no output video stream found in "{url}" ({map=})')

        if not all(ready):
            raise RuntimeError(
                "Given file/url does not pre-provide the media information. Use media.read instead."
            )

        hook = plugins.get_hook()

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            show_log=show_log,
            progress=progress,
            blocksize=blocksize,
            sp_kwargs=sp_kwargs,
            from_bytes=hook.bytes_to_video,
            to_memoryview=hook.video_bytes,
            default_timeout=default_timeout,
        )


class SimpleAudioReader(SimpleReaderBase):

    def __init__(
        self,
        url: FFmpegUrlType,
        *,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int = 1,
        sp_kwargs: dict | None = None,
        stream: str | StreamSpecDict | None = None,
        default_timeout: float | None = None,
        **options,
    ):
        # assign the input stream
        map = "0:a:0" if stream is None else stream_spec_to_map_option(stream)

        args, input_info, ready, output_info, _ = configure.init_media_read(
            [url], [map], options
        )

        if len(output_info) != 1 or output_info[0]["media_type"] != "audio":
            raise FFmpegioError(f'no output audio stream found in "{url}" ({map=})')

        if not all(ready):
            raise RuntimeError(
                "Given file/url does not pre-provide the media information. Use media.read instead."
            )

        hook = plugins.get_hook()

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            show_log=show_log,
            progress=progress,
            blocksize=blocksize,
            sp_kwargs=sp_kwargs,
            from_bytes=hook.bytes_to_audio,
            to_memoryview=hook.audio_bytes,
            default_timeout=default_timeout,
        )


###########################################################################


class SimpleWriterBase(BaseFFmpegRunner):
    def __init__(
        self,
        media_type: MediaType,
        counter: CountDataCallable,
        to_memoryview: ToBytesCallable,
        url: FFmpegUrlType,
        input_rate: int | Fraction,
        input_shape: ShapeTuple | None = None,
        input_dtype: DTypeString | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        overwrite: bool | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        sp_kwargs: dict | None = None,
        options: Unpack[FFmpegOptionDict],
    ):
        """Write video data to a video file

        :param url: output url
        :param input_rate: video frame rate
        :param input_dtype: numpy-style data type string of input frames, defaults
                            to `None` (auto-detect).
        :param input_shape: shapes of each video frame, defaults to `None`
                            (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
        :param overwrite: True to overwrite existing files, defaults to None (auto-set)
        :param show_log: True to show FFmpeg log messages on the console, defaults
                         to None (no show/capture). Ignored if stream format must
                         be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()`
                          or `subprocess.Popen()` call used to run the FFmpeg,
                          defaults to None
        :param options: FFmpeg options, append '_in[input_url_id]' for input
                          option names for specific input url or '_in' to be
                          applied to all inputs. The url-specific option gets
                          the preference (see :doc:`options` for custom options)
        """

        options = {"probesize_in": 32, **options, "r_in": input_rate}
        if overwrite:
            if "n" in options:
                raise FFmpegioError(
                    "cannot specify both `overwrite=True` and `n=ff.FLAG`."
                )
            options["y"] = None

        args, input_info, input_ready, output_info, output_args = (
            configure.init_media_write(
                [url],
                [media_type[0]],
                [(input_rate, None)],
                False,
                None,
                None,
                None,
                extra_inputs,
                options,
                [input_dtype],
                [input_shape],
            )
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info or [],
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_write_outputs,
            deferred_output_args=output_args,
            progress=progress,
            show_log=show_log,
            overwrite=overwrite,
            sp_kwargs={**sp_kwargs, "bufsize": 0} if sp_kwargs else {"bufsize": 0},
        )

        self._get_bytes = to_memoryview
        self._get_num = counter

        # set the default read block size for the referenc stream
        info = self._input_info[0]
        assert "raw_info" in info

        self._rate = info["raw_info"][2]
        self._n0 = 0  # timestamps of the last read sample

        # input data must be initially buffered
        self._deferred_data = [[] for _ in range(len(self._input_info))]

    def _write_deferred_data(self):
        for src, info in zip(self._deferred_data, self._input_info):
            if "writer" in info and len(src):
                writer = info["writer"]
                for data in src:
                    writer.write(data, self.default_timeout)
        self._deferred_data = []
        self._input_ready = True

    def _assign_pipes(self):

        configure.assign_input_pipes(
            self._args["ffmpeg_args"],
            self._input_info,
            self._args["sp_kwargs"],
            use_std_pipes=True,
        )

    @property
    def input_type(self) -> MediaType | None:
        """media type associated with the input streams"""
        info = self._input_info[0]
        return info.get("media_type", None)

    @property
    def input_rate(self) -> int | Fraction | None:
        """sample or frame rates associated with the input streams"""
        info = self._input_info[0]
        return info["raw_info"][2] if "raw_info" in info else None

    @property
    def input_dtype(self) -> DTypeString | None:
        """frame/sample data type associated with the output streams (key)"""
        info = self._input_info[0]
        return info["raw_info"][0] if "raw_info" in info else None

    @property
    def input_shape(self) -> ShapeTuple | None:
        """frame/sample shape associated with the output streams (key)"""
        info = self._input_info[0]
        return info["raw_info"][1] if "raw_info" in info else None

    @property
    def input_count(self) -> int:
        """number of input frames/samples written"""
        return self._n0

    @property
    def input_bytesize(self) -> int|None:
        """input sample/pixel count per frame"""
        return get_bytesize(self.input_shape,self.input_dtype)

    def write(self, data):
        """Write the given numpy.ndarray object, data, and return the number
        of bytes written (always equal to the number of data frames/samples,
        since if the write fails an OSError will be raised).

        When in non-blocking mode, a BlockingIOError is raised if the data
        needed to be written to the raw stream but it couldn’t accept all
        the data without blocking.

        The caller may release or mutate data after this method returns,
        so the implementation should only access data during the method call.

        """

        b = self._get_bytes(obj=data)
        if not len(b):
            return

        if self._input_ready is True:
            logger.debug("[writer main] writing...")
            try:
                self._proc.stdin.write(b)
            except (BrokenPipeError, OSError):
                self._logger.join_and_raise()

        else:
            # need to collect input data type and shape from the actual data
            # before starting the FFmpeg

            configure.update_raw_input(
                self._args["ffmpeg_args"], self._input_info, 0, data
            )

            self._deferred_data[0].append(b)
            self._input_ready = True

            if self._input_ready is True:
                # once data is written for all the necessary inputs,
                # analyze them and start the FFmpeg
                self._open(True)

    def flush(self):
        self._proc.stdin.flush()


class SimpleVideoWriter(SimpleWriterBase):

    def __init__(
        self,
        url: FFmpegUrlType,
        input_rate: int | Fraction,
        *,
        input_shape: ShapeTuple | None = None,
        input_dtype: DTypeString | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        overwrite: bool | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Write video data to a video file

        :param url: output url
        :param input_rate: video frame rate
        :param input_dtype: numpy-style data type string of input frames, defaults
                            to `None` (auto-detect).
        :param input_shape: shapes of each video frame, defaults to `None`
                            (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
        :param overwrite: True to overwrite existing files, defaults to None (auto-set)
        :param show_log: True to show FFmpeg log messages on the console, defaults
                         to None (no show/capture). Ignored if stream format must
                         be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()`
                          or `subprocess.Popen()` call used to run the FFmpeg,
                          defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input
                          option names for specific input url or '_in' to be
                          applied to all inputs. The url-specific option gets
                          the preference (see :doc:`options` for custom options)
        """

        hook = plugins.get_hook()
        super().__init__(
            'video',
            hook.video_frames,
            hook.video_bytes,
            url,
            input_rate,
            input_shape,
            input_dtype,
            extra_inputs,
            overwrite,
            show_log,
            progress,
            sp_kwargs,
            options,
        )

class SimpleAudioWriter(SimpleWriterBase):

    def __init__(
        self,
        url: FFmpegUrlType,
        input_rate: int | Fraction,
        *,
        input_shape: ShapeTuple | None = None,
        input_dtype: DTypeString | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        overwrite: bool | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Write video data to a video file

        :param url: output url
        :param input_rate: video frame rate
        :param input_dtype: numpy-style data type string of input frames, defaults
                            to `None` (auto-detect).
        :param input_shape: shapes of each video frame, defaults to `None`
                            (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
        :param overwrite: True to overwrite existing files, defaults to None (auto-set)
        :param show_log: True to show FFmpeg log messages on the console, defaults
                         to None (no show/capture). Ignored if stream format must
                         be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()`
                          or `subprocess.Popen()` call used to run the FFmpeg,
                          defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input
                          option names for specific input url or '_in' to be
                          applied to all inputs. The url-specific option gets
                          the preference (see :doc:`options` for custom options)
        """

        hook = plugins.get_hook()
        super().__init__(
            'audio',
            hook.audio_frames,
            hook.audio_bytes,
            url,
            input_rate,
            input_shape,
            input_dtype,
            extra_inputs,
            overwrite,
            show_log,
            progress,
            sp_kwargs,
            options,
        )
