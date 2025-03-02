from __future__ import annotations

import logging

logger = logging.getLogger("ffmpegio")

from collections.abc import Sequence
from ._typing import (
    Literal,
    Any,
    RawStreamDef,
    ProgressCallable,
    RawDataBlob,
    Unpack,
    FFmpegUrlType,
)
from .configure import FFmpegOutputUrlComposite, FFmpegInputUrlComposite

import contextlib
from fractions import Fraction

from . import ffmpegprocess, utils, configure, FFmpegError, plugins
from .utils.log import extract_output_stream
from .errors import FFmpegioError

__all__ = ["read", "write"]


def read(
    *urls: * tuple[
        FFmpegInputUrlComposite | tuple[FFmpegUrlType, dict[str, Any] | None]
    ],
    map: Sequence[str] | dict[str, dict[str, Any] | None] | None = None,
    progress: ProgressCallable | None = None,
    show_log: bool | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[dict[str, Any]],
) -> tuple[dict[str, Fraction | int], dict[str, RawDataBlob]]:
    """Read video and audio data from multiple media files

    :param *urls: URLs of the media files to read or a tuple of the URL and its input option dict.
    :param map: FFmpeg map options
    :param progress: progress callback function, defaults to None
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :param use_ya: True if piped video streams uses `ya8` pix_fmt instead of `gray16le`, default to None
    :param **options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                        input url or '_in' to be applied to all inputs. The url-specific option gets the
                        preference (see :doc:`options` for custom options)
    :return: frame/sampling rates and raw data for each requested stream

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          `ffmpegio.video.read()` for each url.

    Specify the streams to return by `map` output option:

        map = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
    'pix_fmt' option is not explicitly set, 'rgb24' is used.

    For audio streams, if 'sample_fmt' output option is not specified, 's16'.
    """

    # initialize FFmpeg argument dict and get input & output information
    args, input_info, output_info = configure.init_media_read(urls, map, options)

    # True if there is unknown datablob info
    need_stderr = any(info["media_info"] is None for info in output_info)

    # run FFmpeg
    capture_log = True if need_stderr else None if show_log else True

    # configure named pipes
    stack = configure.init_named_pipes(args, input_info, output_info)

    def on_exit(rc):
        stack.close()

    # run the FFmpeg
    try:
        proc = ffmpegprocess.Popen(
            args,
            progress=progress,
            capture_log=capture_log,
            sp_kwargs=sp_kwargs,
            on_exit=on_exit,
        )
    except:
        # if Popen failed to start FFmpeg process, need to call the callback
        stack.close()
        raise

    # wait for the FFmpeg to finish processing
    proc.wait()

    # throw error if failed
    if proc.returncode:
        raise FFmpegError(proc.stderr, capture_log)

    # gather output
    rates = {}
    data = {}
    for i, info in enumerate(output_info):
        spec = info["user_map"]
        b = info["reader"].read_all()

        # get datablob info from stderr if needed
        missing = any(v is None for v in info["media_info"])

        if missing:
            logger.warning('Retrieving stream "%s" information from FFmpeg log.', spec)
            new_info = extract_output_stream(proc.stderr, i)

        if info["media_type"] == "video":
            dtype, shape, rate = info["media_info"]

            if missing:
                if dtype is None:
                    pix_fmt = new_info["pix_fmt"]
                    dtype = utils.get_pixel_format(pix_fmt)[0]
                if shape is None:
                    shape = new_info["s"]
                if rate is None:
                    rate = new_info["r"]

            data[spec] = plugins.get_hook().bytes_to_video(
                b=b, dtype=dtype, shape=shape, squeeze=False
            )
        else:  # 'audio'
            dtype, shape, rate = info["media_info"]
            if missing:
                if dtype is None:
                    sample_fmt = new_info["sample_fmt"]
                    dtype = utils.get_audio_format(sample_fmt)
                if shape is None:
                    shape = (new_info["ac"],)
                if rate is None:
                    rate = new_info["ar"]

            data[spec] = plugins.get_hook().bytes_to_audio(
                b=b, dtype=dtype, shape=shape, squeeze=False
            )
        rates[spec] = rate

    return rates, data


def write(
    urls: (
        FFmpegOutputUrlComposite
        | list[FFmpegOutputUrlComposite | tuple[FFmpegOutputUrlComposite, dict]]
    ),
    stream_types: Sequence[Literal["a", "v"]],
    *stream_args: * tuple[RawStreamDef, ...],
    merge_audio_streams: bool | Sequence[int] = False,
    merge_audio_ar: int | None = None,
    merge_audio_sample_fmt: str | None = None,
    merge_audio_outpad: str | None = None,
    progress: ProgressCallable | None = None,
    overwrite: bool | None = None,
    show_log: bool | None = None,
    extra_inputs: Sequence[str | tuple[str, dict]] | None = None,
    sp_kwargs: dict | None = None,
    **options: Unpack[dict[str, Any]],
):
    """write multiple streams to a url/file

    :param url: output url
    :param stream_types: list/string of input stream media types, each element is either 'a' (audio) or 'v' (video)
    :param stream_args: raw input stream data arguments, each input stream is either a tuple of a sample rate (audio) or frame rate (video) followed by a data blob
                         or a tuple of a data blob and a dict of input options. The option dict must include `'ar'` (audio) or `'r'` (video) to specify the rate.
    :param merge_audio_streams: True to combine all input audio streams as a single multi-channel stream. Specify a list of the input stream id's
                                (indices of `stream_types`) to combine only specified streams.
    :param merge_audio_ar: Sampling rate of the merged audio stream in samples/second, defaults to None to use the sampling rate of the first merging stream
    :param merge_audio_sample_fmt: Sample format of the merged audio stream, defaults to None to use the sample format of the first merging stream
    :param progress: progress callback function, defaults to None
    :param overwrite: True to overwrite if output url exists, defaults to None (auto-select)
    :param show_log: True to show FFmpeg log messages on the console, defaults to None (no show/capture)
    :param extra_inputs: list of additional input sources, defaults to None. Each source may be url
                         string or a pair of a url string and an option dict.
    :param sp_kwargs: dictionary with keywords passed to `subprocess.run()` or `subprocess.Popen()` call
                      used to run the FFmpeg, defaults to None
    :param **options: FFmpeg options, append '_in' for input option names (see :doc:`options`). Input options
                      will be applied to all input streams unless the option has been already defined in `stream_data`

    TIPS
    ----

    * All the input streams will be added to the output file by default, unless `map` option is specified
    * If the input streams are of different durations, use `shortest=ffmpegio.FLAG` option to trim all streams to the shortest.
    * Using merge_audio_streams:
      - adds a `filter_complex` global option
      - merged input streams are removed from the `map` option and replaced by the merged stream

    """

    if not isinstance(urls, list):
        urls = [urls]

    args, input_info, output_info, _ = configure.init_media_write(
        urls,
        stream_types,
        stream_args,
        merge_audio_streams,
        merge_audio_ar,
        merge_audio_sample_fmt,
        merge_audio_outpad,
        extra_inputs,
        options,
    )

    if output_info is None:
        raise FFmpegioError("failed to format output...")

    kwargs = {**sp_kwargs} if sp_kwargs else {}
    kwargs.update(
        {
            "progress": progress,
            "overwrite": overwrite,
            "capture_log": None if show_log else False,
        }
    )

    # configure named pipes
    stack = configure.init_named_pipes(args, input_info, output_info)

    # run the FFmpeg
    try:
        proc = ffmpegprocess.Popen(
            args,
            progress=progress,
            capture_log=None if show_log else True,
            sp_kwargs=sp_kwargs,
            on_exit=lambda _: stack.close(),
        )
    except:
        stack.close()
        raise

    # wait for the FFmpeg to finish processing
    proc.wait()

    # throw error if failed
    if proc.returncode:
        raise FFmpegError(proc.stderr, show_log)

    # wind-down the readers
    for info in output_info:
        if "reader" in info:
            info["reader"].cool_down()

    # gather output
    data = {}
    for i, info in enumerate(output_info):
        if info["dst_type"] == "buffer":
            data[i] = info["reader"].read_all()

