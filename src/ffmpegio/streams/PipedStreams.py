from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from typing_extensions import Callable, Literal, Unpack
from .._typing import (
    ProgressCallable,
    InputSourceDict,
    OutputDestinationDict,
    FFmpegOptionDict,
    RawDataBlob,
    ShapeTuple,
    DTypeString,
    MediaType,
)
from ..plugins.hookspecs import FromBytesCallable, CountDataCallable, ToBytesCallable

from collections.abc import Sequence

from ..configure import (
    FFmpegArgs,
    FFmpegInputUrlComposite,
    FFmpegUrlType,
    FFmpegOutputUrlComposite,
    InitMediaOutputsCallable,
)
from ..filtergraph.abc import FilterGraphObject

from fractions import Fraction

from .. import configure, plugins
from ..errors import FFmpegioError
from ..configure import FFmpegArgs, InitMediaOutputsCallable

from .BaseFFmpegRunner import (
    BaseFFmpegRunner as _BaseFFmpegRunner,
    RawInputsMixin as _RawInputsMixin,
    EncodedInputsMixin as _EncodedInputsMixin,
    RawOutputsMixin as _RawOutputsMixin,
    EncodedOutputsMixin as _EncodedOutputsMixin,
)

# fmt:off
__all__ = ["PipedMediaReader", "PipedMediaWriter", "PipedMediaFilter", "PipedMediaTranscoder"]
# fmt:on


class _PipedFFmpegRunner(_BaseFFmpegRunner):
    """Base class to run FFmpeg and manage its multiple I/O's"""

    def __init__(
        self,
        ffmpeg_args: FFmpegArgs,
        input_info: list[InputSourceDict],
        output_info: list[OutputDestinationDict],
        input_ready: Literal[True] | list[bool],
        init_deferred_outputs: InitMediaOutputsCallable | None,
        deferred_output_args: list[FFmpegOptionDict | None],
        *,
        default_timeout: float | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        queuesize: int | None = None,
        sp_kwargs: dict | None = None,
    ):
        """Encoded media stream transcoder

        :param ffmpeg_args: (Mostly) populated FFmpeg argument dict
        :param input_info: FFmpeg output option dicts of all the output pipes. Each dict
                               must contain the `"f"` option to specify the media format.
        :param output_info: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param input_ready: indicates if input is ready (True) or need its first batch of data to
                            provide necessary information for the outputs
        :param init_deferred_outputs: function to initialize the outputs which have been deferred to
                                      configure until the first batch of input data is in
        :param deferred_output_args:
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        :param options: global/default FFmpeg options. For output and global options,
                        use FFmpeg option names as is. For input options, append "_in" to the
                        option name. For example, r_in=2000 to force the input frame rate
                        to 2000 frames/s (see :doc:`options`). These input and output options
                        specified here are treated as default, common options, and the
                        url-specific duplicate options in the ``inputs`` or ``outputs``
                        sequence will overwrite those specified here.
        """

        super().__init__(
            ffmpeg_args,
            input_info,
            output_info,
            input_ready,
            init_deferred_outputs,
            deferred_output_args,
            default_timeout,
            progress,
            show_log,
            sp_kwargs,
        )

        # set the default read block size for the referenc stream
        self._pipe_kws = {"queue_size": queuesize}

    def _assign_pipes(self):
        """pre-popen pipe assignment and initialization

        All named pipes must be
        """
        if len(self._input_info):
            configure.assign_input_pipes(
                self._args["ffmpeg_args"],
                self._input_info,
                self._args["sp_kwargs"],
            )

        if len(self._output_info):
            configure.assign_output_pipes(
                self._args["ffmpeg_args"],
                self._output_info,
                self._args["sp_kwargs"],
            )

        configure.init_named_pipes(
            self._input_info, self._output_info, **self._pipe_kws, stack=self._stack
        )


class PipedMediaReader(_EncodedInputsMixin, _RawOutputsMixin, _PipedFFmpegRunner):

    def __init__(
        self,
        *urls: *tuple[FFmpegInputUrlComposite | tuple[FFmpegUrlType, FFmpegOptionDict]],
        map: Sequence[str] | dict[str, FFmpegOptionDict] | None = None,
        ref_stream: int = 0,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Read video and audio data from multiple media files

        :param *urls: URLs of the media files to read or a tuple of the URL and its input option dict.
        :param map: FFmpeg map options
        :param ref_stream: index of the reference stream to pace read operation, defaults to 0. The
                           reference stream is guaranteed to have a frame data on every read operation.
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)

        Note: To read a single stream from a single source, use `audio.read()`, `video.read()` or `image.read()`
              for reducing the overhead

        Specify the streams to return by `map` output option:

            map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

        Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
        'pix_fmt' option is not explicitly set, 'rgb24' is used.

        For audio streams, if 'sample_fmt' output option is not specified, 's16'.
        """

        # initialize FFmpeg argument dict and get input & output information
        args, input_info, ready, output_info, output_args = configure.init_media_read(
            urls, map, {"probesize_in": 32, **options}
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=ready,
            init_deferred_outputs=configure.init_media_read_outputs,
            deferred_output_args=output_args,
            ref_output=ref_stream,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )

        hook = plugins.get_hook()
        self._get_bytes = {"video": hook.video_bytes, "audio": hook.audio_bytes}

    def __iter__(self):
        return self

    def __next__(self):
        F = self.read(self._blocksize, self.default_timeout)
        # if not any(
        #     len(self._get_bytes[info["media_type"]](obj=f))
        #     for f, info in zip(F.values(), self._output_info)
        # ):
        if plugins.get_hook().is_empty(obj=F):
            raise StopIteration
        return F


class PipedMediaWriter(_EncodedOutputsMixin, _RawInputsMixin, _PipedFFmpegRunner):

    def __init__(
        self,
        urls: (
            FFmpegOutputUrlComposite
            | list[
                FFmpegOutputUrlComposite
                | tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
            ]
        ),
        stream_types: Sequence[Literal["a", "v"]],
        *input_rates_or_opts: *tuple[int | Fraction | FFmpegOptionDict, ...],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        merge_audio_streams: bool | Sequence[int] = False,
        merge_audio_ar: int | None = None,
        merge_audio_sample_fmt: str | None = None,
        merge_audio_outpad: str | None = None,
        overwrite: bool | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Write video and audio data from multiple media streams to one or more files

        :param url: output url
        :param stream_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
        :param input_rates_or_opts: either sample rate (audio) or frame rate (video)
                                     or a dict of input options. The option dict must
                                     include `'ar'` (audio) or `'r'` (video) to specify
                                     the rate.
        :param input_dtypes: list of numpy-style data type strings of input samples
                          or frames of input media streams, defaults to `None`
                          (auto-detect).
        :param input_shapes: list of shapes of input samples or frames of input media
                          streams, defaults to `None` (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                            string or a pair of a url string and an option dict.
        :param merge_audio_streams: True to combine all input audio streams as a single multi-channel stream. Specify a list of the input stream id's
                                    (indices of `stream_types`) to combine only specified streams.
        :param merge_audio_ar: Sampling rate of the merged audio stream in samples/second, defaults to None to use the sampling rate of the first merging stream
        :param merge_audio_sample_fmt: Sample format of the merged audio stream, defaults to None to use the sample format of the first merging stream
        :param overwrite: True to overwrite existing files, defaults to None (auto-set)
        :param show_log: True to show FFmpeg log messages on the console,
                        defaults to None (no show/capture)
                        Ignored if stream format must be retrieved automatically.
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                            input url or '_in' to be applied to all inputs. The url-specific option gets the
                            preference (see :doc:`options` for custom options)
        """

        if not isinstance(urls, list):
            urls = [urls]

        options = {"probesize_in": 32, **options}
        if overwrite:
            if "n" in options:
                raise FFmpegioError(
                    "cannot specify both `overwrite=True` and `n=ff.FLAG`."
                )
            options["y"] = None

        stream_args = [
            (None, v) if isinstance(v, dict) else (v, None) for v in input_rates_or_opts
        ]
        args, input_info, input_ready, output_info, output_args = (
            configure.init_media_write(
                urls,
                stream_types,
                stream_args,
                merge_audio_streams,
                merge_audio_ar,
                merge_audio_sample_fmt,
                merge_audio_outpad,
                extra_inputs,
                {"probesize_in": 32, **options},
                input_dtypes,
                input_shapes,
            )
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_write_outputs,
            deferred_output_args=output_args,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            blocksize=blocksize,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )


class PipedMediaFilter(_RawOutputsMixin, _RawInputsMixin, _PipedFFmpegRunner):

    def __init__(
        self,
        expr: str | FilterGraphObject | Sequence[str | FilterGraphObject],
        input_types: Sequence[Literal["a", "v"]],
        *input_rates_or_opts: *tuple[int | Fraction | FFmpegOptionDict, ...],
        input_dtypes: list[DTypeString] | None = None,
        input_shapes: list[ShapeTuple] | None = None,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        ref_output: int = 0,
        output_options: dict[str, FFmpegOptionDict] | None = None,
        show_log: bool | None = None,
        progress: ProgressCallable | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict | None = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Filter audio/video data streams with FFmpeg filtergraphs

        :param expr: complex filtergraph expression or a list of filtergraphs
        :param input_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
        :param input_rates_or_opts: raw input stream data arguments, each input stream is either a tuple of a sample rate (audio) or frame rate (video) followed by a data blob
                                    or a tuple of a data blob and a dict of input options. The option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
        :param input_dtypes: list of numpy-style data type strings of input samples
                             or frames of input media streams, defaults to `None`
                             (auto-detect).
        :param input_shapes: list of shapes of input samples or frames of input media
                             streams, defaults to `None` (auto-detect).
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param ref_output: index or label of the reference stream to pace read operation, defaults to 0.
                           `PipedMediaFilter.read()` operates around the reference stream.
        :param output_options: specific options for keyed filtergraph output pads.
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param progress: progress callback function, defaults to None
        :param blocksize: Background reader thread blocksize (how many reference stream frames/samples to read at once from FFmpeg)
        :                 defaults to `None` to use 1 video frame or 1024 audio frames
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                        used to run the FFmpeg, defaults to None
        :param **options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                        will be applied to all input streams unless the option has been already defined in `stream_data`
        """

        input_args = [
            (None, v) if isinstance(v, dict) else (v, None) for v in input_rates_or_opts
        ]

        (
            args,
            input_info,
            input_ready,
            output_info,
            deferred_output_args,
        ) = configure.init_media_filter(
            expr,
            input_types,
            input_args,
            extra_inputs,
            input_dtypes,
            input_shapes,
            {"probesize_in": 32, **options},
            output_options or {},
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=input_ready,
            init_deferred_outputs=configure.init_media_filter_outputs,
            deferred_output_args=deferred_output_args,
            ref_output=ref_output,
            blocksize=blocksize,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )


class PipedMediaTranscoder(_EncodedOutputsMixin, _EncodedInputsMixin, _PipedFFmpegRunner):
    """Class to transcode encoded media streams"""

    def __init__(
        self,
        input_options: Sequence[FFmpegOptionDict],
        output_options: Sequence[FFmpegOptionDict],
        *,
        extra_inputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        extra_outputs: Sequence[str | tuple[str, FFmpegOptionDict]] | None = None,
        progress: ProgressCallable | None = None,
        show_log: bool | None = None,
        blocksize: int | None = None,
        queuesize: int | None = None,
        default_timeout: float | None = None,
        sp_kwargs: dict = None,
        **options: Unpack[FFmpegOptionDict],
    ):
        """Encoded media stream transcoder

        :param input_options: FFmpeg input option dicts of all the input pipes. Each dict
                              must contain the `"f"` option to specify the media format.
        :param output_options: FFmpeg output option dicts of all the output pipes. Each dict
                               must contain the `"f"` option to specify the media format.
        :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                             string or a pair of a url string and an option dict.
        :param extra_outputs: list of additional output destinations, defaults to None. Each destination
                              may be url string or a pair of a url string and an option dict.
        :param progress: progress callback function, defaults to None
        :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
        :param blocksize: Background reader thread blocksize, defaults to `None` to use 64-kB blocks
        :param queuesize: Background reader & writer threads queue size, defaults to `None` (unlimited)
        :param default_timeout: Default read timeout in seconds, defaults to `None` to wait indefinitely
        :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or
                        `subprocess.Popen()` call used to run the FFmpeg, defaults
                        to None
        :param options: global/default FFmpeg options. For output and global options,
                        use FFmpeg option names as is. For input options, append "_in" to the
                        option name. For example, r_in=2000 to force the input frame rate
                        to 2000 frames/s (see :doc:`options`). These input and output options
                        specified here are treated as default, common options, and the
                        url-specific duplicate options in the ``inputs`` or ``outputs``
                        sequence will overwrite those specified here.
        """

        args, input_info, output_info = configure.init_media_transcoder(
            [("pipe", opts) for opts in input_options],
            [("pipe", opts) for opts in output_options],
            extra_inputs,
            extra_outputs,
            {"y": None, **options},
        )

        super().__init__(
            ffmpeg_args=args,
            input_info=input_info,
            output_info=output_info,
            input_ready=None,
            init_deferred_outputs=None,
            deferred_output_args=None,
            default_timeout=default_timeout,
            progress=progress,
            show_log=show_log,
            blocksize=blocksize,
            queuesize=queuesize,
            sp_kwargs=sp_kwargs,
        )
