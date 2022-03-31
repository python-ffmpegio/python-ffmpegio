from io import BytesIO

from . import ffmpegprocess, utils, configure, FFmpegError
from .utils import avi

__all__ = ["read"]


def read(*urls, progress=None, show_log=None, **options):
    """Read video and audio frames

    :param *urls: URLs of the media files to read.
    :type *urls: tuple(str)
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param use_ya: True if piped video streams uses `ya8` pix_fmt instead of `gray16le`, default to None
    :type use_ya: bool, optional
    :param \\**options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                        input url or '_in' to be applied to all inputs. The url-specific option gets the
                        preference (see :doc:`options` for custom options)
    :type \\**options: dict, optional

    :return: frame rate and video frame data, created by `bytes_to_video` plugin hook
    :rtype: (`fractions.Fraction`, object)

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          `ffmpegio.video.read()` for each url.


    Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
    'pix_fmt' option is not explicitly set, 'rgb24' is used.

    For audio streams, if 'sample_fmt' output option is not specified, 's16'.


    streams = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    """

    ninputs = len(urls)
    if not ninputs:
        raise ValueError("At least one URL must be given.")

    # separate the options
    spec_inopts = utils.pop_extra_options_multi(options, r"_in(\d+)$")
    inopts = utils.pop_extra_options(options, "_in")

    # create a new FFmpeg dict
    args = configure.empty()
    configure.add_url(args, "output", "-", options)  # add piped output
    for i, url in enumerate(urls):  # add inputs
        opts = {**inopts, **spec_inopts.get(i, {})}
        # check url (must be url and not fileobj)
        configure.check_url(
            url, nodata=True, nofileobj=True, format=opts.get("f", None)
        )
        configure.add_url(args, "input", url, opts)

    # configure output options
    use_ya = configure.finalize_media_read_opts(args)

    # run FFmpeg
    out = ffmpegprocess.run(
        args,
        progress=progress,
        capture_log=None if show_log else True,
    )
    if out.returncode:
        raise FFmpegError(out.stderr, show_log)

    # fire up the AVI reader and process the stdout bytes
    # TODO: Convert to use pipe/thread
    reader = avi.AviReader()
    reader.start(BytesIO(out.stdout), use_ya)
    # get frame rates and sample rates of all media streams
    rates = {
        v["spec"]: v["frame_rate"] if v["type"] == "v" else v["sample_rate"]
        for v in reader.streams.values()
    }
    data = {k: [] for k in reader.streams}
    for st, frame in reader:
        data[st].append(frame)

    data = {
        reader.streams[k]["spec"]: reader.from_bytes(k, b"".join(v))
        for k, v in data.items()
    }

    return rates, data
