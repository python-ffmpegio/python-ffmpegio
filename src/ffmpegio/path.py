from os import path as _path, name as _os_name
from shutil import which
from subprocess import run, PIPE
import re, shlex, subprocess as sp
from packaging.version import Version

from . import plugins

# add FFmpeg directory to the system path as given in system environment variable FFMPEG_DIR
FFMPEG_BIN = None
FFPROBE_BIN = None
FFMPEG_VER = None


def found():
    """`True` if ffmpeg and ffprobe binaries are located

    :return: True if both ffmpeg and ffprobe are found
    :rtype: bool
    """
    return bool(FFMPEG_BIN and FFPROBE_BIN)


def where(probe=False):
    """Get the path to FFmpeg/FFprobe executable

    :param probe: True to return FFprobe path instead, defaults to False
    :type probe: bool, optional
    :return: Path to FFmpeg/FFprobe exectutable
    :rtype: str or None
    """

    path = FFPROBE_BIN if probe else FFMPEG_BIN

    if not path:
        raise Exception(
            "FFmpeg executables not found. Run `ffmpegio.set_path()` first or place FFmpeg executables in auto-detectable path locations."
        )

    return path


def find(ffmpeg_path=None, ffprobe_path=None):
    """Set FFmpeg and FFprobe executables

    :param ffmpeg_path: Full path to either the ffmpeg executable file or
                        to the folder housing both ffmpeg and ffprobe, defaults to None
    :type ffmpeg_path: str, optional
    :param ffprobe_path: Full path to the ffprobe executable file, defaults to None
    :type ffprobe_path: str, optional

    If `ffmpeg_path` specifies a directory, the names of the executables are
    auto-set to `ffmpeg` and `ffprobe`.

    If the file locations are specified, the presence of the files will be
    tested and an exception will be raised if both ffmpeg and ffprobe are not
    valid executables.

    If no argument is specified, the executables are auto-detected in the following orders.
    (1) `ffmpeg` and `ffprobe` commands, i.e., the path to the parent directory
        is included in the system PATH environmental variable.
    (2) Run the `finder` plugin functions in the LIFO order and use the first valid
        paths. There are two plugins currently offered: `ffmpegio-plugin-downloader`
        and `ffmpegio-plugin-static-ffmpeg`.
    (3) In Windows, additional locations are searched (e.g., C:\Program Files\ffmpeg).
        See the documentation for the full list.

    """

    global FFMPEG_BIN, FFPROBE_BIN, FFMPEG_VER

    has_ffmpeg = ffmpeg_path is not None
    has_ffprobe = ffprobe_path is not None
    has_ffdir = has_ffmpeg and _path.isdir(ffmpeg_path)

    if (has_ffmpeg != has_ffprobe) and (not has_ffdir or has_ffprobe):
        raise ValueError(
            "Either specify paths of both ffmpeg and ffprobe or a path to the directory containing both."
        )

    if has_ffdir:
        ext = ".exe" if _os_name == "nt" else ""
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
        ffmpeg_bin = ffmpeg_path
        ffprobe_bin = ffprobe_path
    elif which("ffmpeg") and which("ffprobe"):
        ffmpeg_bin = "ffmpeg"
        ffprobe_bin = "ffprobe"
    else:
        res = plugins.get_hook().finder()
        if res is None:
            raise RuntimeError("Failed to auto-detect ffmpeg and ffprobe executable.")
        FFMPEG_BIN, FFPROBE_BIN = res


def _exec(args, **other_run_args):
    """just run ffmpeg without bells-n-whistles

    :param args: FFmpeg command arguments without `ffmpeg`
    :type args: str or Sequence[str]
    :param **other_run_args: subprocess.run() options
    :type **other_run_args: dict
    """
    if isinstance(args, str):
        args = shlex.split(args)
    return sp.run((where(), *args), **other_run_args)


def versions():
    """Get FFmpeg version and configuration information

    :return: versions of ffmpeg and its av libraries as well as build configuration
    :rtype: dict

    ==================  ====  =========================================
    key                 type  description
    ==================  ====  =========================================
    'version'           str   FFmpeg version
    'configuration'     list  list of build configuration options
    'library_versions'  dict  version numbers of dependent av libraries
    ==================  ====  =========================================

    """
    s = _exec(
        ["-version"], stdout=PIPE, universal_newlines=True, encoding="utf-8"
    ).stdout.splitlines()
    v = dict(version=re.match(r"ffmpeg version (\S+)", s[0])[1])
    i = 2 if s[1].startswith("built with") else 1
    if s[i].startswith("configuration:"):
        v["configuration"] = sorted([m[1] for m in re.finditer(r"\s--(\S+)", s[i])])
        i += 1
    lv = None
    for l in s[i:]:
        m = re.match(r"(\S+)\s+(.+?) /", l)
        if m:
            if lv is None:
                lv = v["library_versions"] = {}
            lv[m[1]] = m[2].replace(" ", "")
    return v