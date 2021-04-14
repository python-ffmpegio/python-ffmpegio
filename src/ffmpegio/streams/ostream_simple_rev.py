"""
ffmpegio.video.open()
ffmpegio.video.read()
ffmpegio.video.write()
"""

import sys, json, subprocess as sp
import numpy as np
import ffmpeg

from . import utils


def process_frames_reverse(videofile, callback, **kwargs):
    """capture video frames

    Parameters:
        videofile (str): input media file path
        callback (Callable): takes
        ss or ssframe (number): starting position in seconds
        t (number): limit the duration of data read from the input file in seconds.
        to (number): Stop writing the output or reading the input at position
        fmt (str): output frame format (default: rgb24, see _pix_fmt_list for options)
        vframes (number): number of frames to retrieve at a time
        filters (list): list of arguments to ffmpeg.filter() to define FFmpeg filtergraph

    Returns numpy array of the requested video frames
    """

    (inopts, filters, outopts) = _process_args(videofile, **kwargs)
    (dtype, shape, tframes) = get_frame_info(videofile, **kwargs, need_tframes=True)

    vframes = outopts.get("vframes", 1)
    framebytes = np.prod(shape[1:])
    nbytes = vframes * framebytes * np.dtype(dtype).itemsize
    shape = (-1, *shape[1:])

    ss = inopts.get("ss")
    t = inopts.get("t", 0)
    to = inopts.get("to", ss - t)

    process = sp.Popen(
        [
            sys.executable,
            "-m",
            "hsvanalysis.media_access",
            videofile,
            str(ss),
            str(to),
            str(tframes),
            outopts["pix_fmt"],
            json.dumps(filters),
        ],
        stdout=sp.PIPE,
        stderr=sp.PIPE,
    )

    canceled = False
    while not canceled:
        out = process.stdout.read(nbytes)
        if out:
            frames = np.frombuffer(out, dtype).reshape(shape)
            canceled = callback(frames)

        process.poll()
        if process.returncode is not None:
            if process.returncode > 0:
                err = process.stderr.read()
                raise Exception(err.decode("utf-8"))
            break

    if canceled:
        process.terminate()
        process.wait()

    return canceled


def _rbreader(videofile, ss, to, Tblk, **kwargs):

    (_, filters, outopts) = _process_args(videofile, **kwargs)
    t0 = ss - Tblk
    while t0 >= to:
        try:
            out, err = _ffmpeg_output(
                videofile, {"ss": t0, "t": Tblk}, outopts, filters
            ).run(quiet=True)
        except ffmpeg.Error as err:
            raise Exception(err.stderr.decode("utf-8"))
        sys.stdout.buffer.write(out)
        t0 -= Tblk

    if t0 < to:
        out, _ = _ffmpeg_output(
            videofile, {"ss": to, "to": t0 + Tblk}, outopts, filters
        ).run(capture_stdout=True, quiet=True)
        sys.stdout.buffer.write(out)


# initially use FFMPEG_DIR system environment variable
if not set_ffmpeg_dir(os.getenv("FFMPEG_PATH") or os.getenv("FFMPEG_DIR")):
    logging.warn(
        "FFmpeg binaries not found. Use hsvanalysis.set_ffmpeg_dir() to add their parent folder to the system path."
    )

__all__ = [
    "get_ffmpeg_dir",
    "set_ffmpeg_dir",
    "get_format_info",
    "get_video_codec_info",
    "capture_frames",
    "process_frames",
    "process_frames_reverse",
]

if __name__ == "__main__":
    # to run the helper spawned subprocess for process_frames_reverse()
    videofile = sys.argv[1]
    ss = float(sys.argv[2])
    to = float(sys.argv[3])
    Tblk = float(sys.argv[4])
    fmt = sys.argv[5]
    filters = json.loads(sys.argv[6])

    _rbreader(videofile, ss, to, Tblk, fmt=fmt, filters=filters)
