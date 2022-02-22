from os import path as _path, name as _os_name
from shutil import which

from . import plugins

# add FFmpeg directory to the system path as given in system environment variable FFMPEG_DIR
FFMPEG_BIN = None
FFPROBE_BIN = None


def found():
    """`True` if ffmpeg and ffprobe binaries are located

    :return: True if both ffmpeg and ffprobe are found
    :rtype: bool
    """
    return bool(FFMPEG_BIN and FFPROBE_BIN)


def where():
    """Get current path to FFmpeg bin directory

    :return: path to FFmpeg bin directory or `None` if ffmpeg and ffprobe paths have not been set.
    :rtype: str or None
    """
    return _path.dirname(FFMPEG_BIN) if found() else None


def find(ffmpeg_path=None, ffprobe_path=None):

    global FFMPEG_BIN, FFPROBE_BIN

    has_ffmpeg = ffmpeg_path is not None
    has_ffprobe = ffprobe_path is not None
    has_ffdir = has_ffmpeg and _path.isfile(ffmpeg_path)

    if (has_ffdir and has_ffprobe) or (has_ffmpeg != has_ffprobe):
        raise ValueError(
            "Either specify paths of both ffmpeg and ffprobe or a path to the directory containing both."
        )

    if has_ffdir:
        ext = ".exe" if _os_name != "nt" else ""
        ffdir = ffmpeg_path
        ffmpeg_path = _path.join(ffdir, f"ffmpeg{ext}")
        ffprobe_path = _path.join(ffdir, f"ffprobe{ext}")

    if has_ffmpeg:
        if not which(ffmpeg_path):
            raise ValueError(
                f"ffmpeg not found in {ffdir}"
                if has_ffdir
                else f"ffmpeg executable not found or {ffmpeg_path}"
            )
        elif not which(ffprobe_path):
            raise ValueError(
                f"ffprobe not found in {ffdir}"
                if has_ffdir
                else f"ffprobe executable not found or {ffprobe_path}"
            )
        FFMPEG_BIN = ffmpeg_path
        FFPROBE_BIN = ffprobe_path
    elif which("ffmpeg") and which("ffprobe"):
        FFMPEG_BIN = "ffmpeg"
        FFPROBE_BIN = "ffprobe"
    else:
        res = plugins.get_hook().finder()
        if res is None:
            raise RuntimeError("Failed to auto-detect ffmpeg and ffprobe executable.")
        FFMPEG_BIN, FFPROBE_BIN = res


def get_ffmpeg(probe=False):

    path = FFPROBE_BIN if probe else FFMPEG_BIN

    if not path:
        raise Exception(
            "FFmpeg executables not found. Run `ffmpegio.set_path()` first or place FFmpeg executables in auto-detectable path locations."
        )

    return path
