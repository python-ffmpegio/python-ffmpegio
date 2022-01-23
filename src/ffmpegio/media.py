import numpy as np
import re
from io import BytesIO

from . import ffmpegprocess, utils, configure, FFmpegError, probe
from .utils import avi


def read(*urls, streams=None, progress=None, show_log=None, **options):
    """Read video frames

    :param *urls: URLs of the media files to read.
    :type *urls: tuple(str)
    :param streams: list of file + stream specifiers or filtergraph label to output, alias of `map` option,
                    defaults to None, which outputs at most one video and one audio, selected by FFmpeg
    :type streams: seq(str), optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param use_ya8: True if piped video streams uses `ya8` pix_fmt instead of `gray16le`, default to None
    :type use_ya8: bool, optional
    :param \\**options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                        input url or '_in' to be applied to all inputs. The url-specific option gets the
                        preference (see :doc:`options` for custom options)
    :type \\**options: dict, optional

    :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
    :rtype: (`fractions.Fraction`, `numpy.ndarray`)

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          `ffmpegio.video.read()` for each url.


    Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
    'pix_fmt' option is not explicitly set, 'rgb24' is used.

    For audio streams, if 'sample_fmt' output option is not specified, 's16le'.


    streams = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    """

    ninputs = len(urls)
    if not ninputs:
        raise ValueError("At least one URL must be given.")

    # separate the options
    spec_inopts = utils.pop_extra_options_multi(options, r"_in(\d+)$")
    inopts = utils.pop_extra_options(options, "_in")

    # check to make sure all pixel and sample formats are supported
    gray16le = ya8 = 0
    for k in utils.find_stream_options(options, "pix_fmt"):
        v = options[k]
        utils.get_video_format(v)
        if v == "gray16le":
            gray16le += 1
        elif v == "ya8":
            ya8 += 1
    if gray16le and ya8:
        raise ValueError("gray16le and ya8 pix_fmts cannot be mixed.")

    # if pix_fmt and sample_fmt not specified, set defaults
    # user can conditionally override these by stream-specific option
    if "pix_fmt" not in options:
        options["pix_fmt"] = "rgb24"
    if "sample_fmt" not in options:
        options["sample_fmt"] = "s16"

    # add output formats and codecs
    options["f"] = "avi"
    options["c:v"] = "rawvideo"

    # add audio codec
    for k in utils.find_stream_options(options, "sample_fmt"):
        options[f"c:a" + k[10:]] = utils.get_audio_format(options[k])[0]

    # create a new FFmpeg dict
    args = configure.empty()
    configure.add_url(args, "output", "-", options)  # add piped output
    for i, url in enumerate(urls):  # add inputs
        # check url (must be url and not fileobj)
        configure.check_url(url, nodata=True, nofileobj=True)
        configure.add_url(args, "input", url, {*inopts, *spec_inopts.get(i, {})})

    # map
    if streams is not None:
        # separate file ids (if present)
        def split_file_id(s):
            try:
                m = re.match(r"(\d+):", s)
                s = s[m.end() :]
                return (int(m[1]), s[m.end() :]) if m else (None, s)
            except:
                try:
                    assert len(s) > 1
                    fid = int(s[0])
                    return (fid, s[1:])
                except:
                    return (None, s)

        streams = [split_file_id(s) for s in streams]

        if ninputs == 1:
            streams = [(0, s[1]) if s[0] is None else s for s in streams]
        elif any((s for s in streams if s[0] is None)):
            raise ValueError(
                'multi-url mode requires to specify the file associated with each stream. e.g., "0:v:0"'
            )

        # overrides map option if set
        args["outputs"][0]["map"] = [
            (fid, *s) if isinstance(s, (str, int)) else (fid, s) for fid, s in streams
        ]

    out = ffmpegprocess.run(
        args,
        progress=progress,
        capture_log=False if show_log else True,
    )
    if out.returncode:
        raise FFmpegError(out.stderr)

    # fire up the AVI reader and process the stdout bytes
    reader = avi.AviReader(BytesIO(out.stdout), ya8)
    # get frame rates and sample rates of all media streams
    rates = {
        v["spec"]: v["frame_rate"] if v["type"] == "v" else v["sample_rate"]
        for v in reader.streams.values()
    }
    # get data first by accumulating all the AVI packets then concatenate to form the final arrays
    data = {v["spec"]: [] for v in reader.streams.values()}
    for st, frame in reader:
        data[st].append(frame)
    data = {k: np.concatenate(v) for k, v in data.items()}

    return rates, data
