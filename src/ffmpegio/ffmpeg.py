import shlex as _shlex, shutil as _shutil
from collections import abc
from .utils import filter as filter_utils

import subprocess as _sp
from subprocess import DEVNULL, PIPE

import re as _re, os as _os, logging as _logging

form_shell_cmd = (
    _shlex.join
    if hasattr(_shlex, "join")
    else lambda args: " ".join(_shlex.quote(arg) for arg in args)
)


def parse_options(args):
    """parse command-line option arguments

    :param args: argument string or sequence of arguments
    :type args: str or seq of str
    :return: parsed options. Flag options get None as their values.
    :rtype: dict
    """
    if isinstance(args, str):
        args = _shlex.split(args)
    res = {}
    n = len(args)
    i = 0
    while i < n:
        key = args[i][1:]
        i += 1
        if i < n and args[i][0] != "-":
            if key not in res:
                res[key] = args[i]
            elif isinstance(res[key], str):
                res[key] = [res[key], args[i]]
            else:
                res[key].append(args[i])
            i += 1
        else:
            res[key] = None
    return res


def parse(cmdline):
    """parse ffmpeg command line arguments

    :param cmdline: full or partial ffmpeg command line string
    :type cmdline: str or seq(str)
    :return: ffmpegio FFmpeg argument dict
    :rtype: dict
    """

    from .caps import options

    if isinstance(cmdline, str):
        # remove multi-line command
        cmdline = _re.sub(r"\\\n", " ", cmdline)

        # split the command line into its options
        args = _shlex.split(cmdline)
    else:  # list of strs
        args = cmdline

    # exclude 'ffmpeg' command if present
    if _re.search(r'(?:^|[/\\])?ffmpeg(?:.exe)?"?$', args[0], _re.IGNORECASE):
        args = args[1:]

    # extract global options
    all_gopts = options("global")
    all_lopts = options("per-file")
    is_gopt = [len(s) and s[0] == "-" and s[1:] in all_gopts for s in args]
    is_lopt = [not tf for tf in is_gopt]
    gopts = {}
    for i, s in enumerate(args):
        if not is_gopt[i]:
            continue
        k = s[1:]
        if k in ('h','?','help','-help'): # special case take all args thereafter
            gopts[k] = ' '.join(args[i+1:])
        elif all_gopts[k] is None:
            gopts[k] = None
        else:
            gopts[k] = args[i + 1]
            is_lopt[i + 1] = False

    args = [s for s, tf in zip(args, is_lopt) if tf]

    # identify -i options
    ipos = [i + 2 for i, v in enumerate(args) if v == "-i"]
    inputs = [
        (args[i1 - 1], parse_options(args[i0 : i1 - 2]))
        for i0, i1 in zip((0, *ipos[:-1]), ipos)
    ]
    if len(inputs):
        args = args[ipos[-1] :]  # drop all input arguments

    # identify output_urls
    opos = [
        i + 1
        for i, v in enumerate(args)
        if v[0] != "-"  # must not be an option name/flag
        and (
            i == 0  # no output options
            or args[i - 1][0] != "-"  # prev arg specifies an output option value
            or all_lopts.get(args[i - 1][1:].split(":", 1)[0], False)
            is None  # prev arg is a flag
        )
    ]
    outputs = [
        (args[i1 - 1], parse_options(args[i0 : i1 - 1]))
        for i0, i1 in zip((0, *opos[:-1]), opos)
    ]

    return dict(global_options=gopts, inputs=inputs, outputs=outputs)


def compose(args, command="", shell_command=False):
    """compose ffmpeg subprocess arguments from argument dict values

    :param global_options: global options, defaults to None
    :type global_options: dict, optional
    :param inputs: list of input files and their options, defaults to []
    :type inputs: seq of seq(str, dict or None), optional
    :param outputs: list of output files and thier options, defaults to []
    :type outputs: seq of seq(str, dict or None), optional
    :param command: ffmpeg command, defaults to ""
    :type command: str, optional
    :param shell_command: True to output shell command ready string, defaults to False
    :type shell_command: bool, optional
    :returns: list of arguments (possibly missing the leading 'ffmpeg' command if `command`
              is not given) or shell command string if `shell_command` is True
    :rtype: list of str or str

    If global_options is None and only 1 output file given, FFmpeg global options
    may be specified as additional output options.
    """

    def finalize_global(key, val):
        if key in ("filter_complex", "lavfi"):
            val = filter_utils.compose(val)
        return key, val

    def finalize_output(key, val):
        if key in ("vf", "af") or _re.match(r"filter(?:\:|$)?", key):
            val = filter_utils.compose(val)
        elif _re.match(r"s(?:\:|$)", key) and not isinstance(val, str):
            val = "x".join((str(v) for v in val))
        elif key == "map" and not isinstance(val, str):
            # if an entry is a seq, join with ':'
            val = [
                v if isinstance(v, str) else ":".join((str(vi) for vi in v))
                for v in val
            ]
        return key, val

    def finalize_input(key, val):
        if _re.match(r"s(?:\:|$)", key) and not isinstance(val, str):
            val = "x".join((str(v) for v in val))
        return key, val

    def opts2args(opts, finalize):
        args = []
        for itm in opts.items():
            key, val = finalize(*itm)

            karg = f"-{key}"
            if not isinstance(val, str) and isinstance(val, abc.Sequence):
                for v in val:
                    args.extend([karg, str(v)])
            else:
                args.append(karg)
                if val is not None:
                    args.append(str(val))
        return args

    def inputs2args(inputs):
        args = []
        for url, opts in inputs:
            if opts:
                args.extend(opts2args(opts, finalize_input))
            args.extend(
                [
                    "-i",
                    url
                    if url is not None
                    else "/dev/null"
                    if _os.name != "nt"
                    else "NUL",
                ]
            )
        return args

    def outputs2args(outputs):
        args = []
        for url, opts in outputs:
            if opts:
                args.extend(opts2args(opts, finalize_output))
            args.append(
                url if url is not None else "/dev/null" if _os.name != "nt" else "NUL"
            )
        return args

    args = [
        *([command] if command else []),
        *opts2args(args.get("global_options", None) or {}, finalize_global),
        *inputs2args(args.get("inputs", None) or ()),
        *outputs2args(args.get("outputs", None) or ()),
    ]
    return form_shell_cmd(args) if shell_command else args


# add FFmpeg directory to the system path as given in system environment variable FFMPEG_DIR
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"


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
    return _os.path.dirname(FFMPEG_BIN) if found() else None


def find(dir=None):
    """Set path to FFmpeg bin directory

    :param dir: full path of the FFmpeg bin directory, defaults to None, which
                only look in the default locations
    :type dir: str, optional
    :raises Exception: if failed to find ffmpeg or ffprobe binary

    In Linux and Mac, only the specified directory or the system path are
    checked. In Windows, the following additional paths are tested in this order:

    * ``%PROGRAMFILES%\\ffmpeg\\bin``
    * ``%PROGRAMFILES(X86)%\\ffmpeg\\bin``
    * ``%USERPROFILE%\\ffmpeg\\bin``
    * ``%APPDATA%\\ffmpeg\\bin``
    * ``%APPDATA%\\programs\\ffmpeg\\bin``
    * ``%LOCALAPPDATA%\\ffmpeg\\bin``
    * ``%LOCALAPPDATA%\\programs\\ffmpeg\\bin``

    Here, ``%xxx%`` are the standard Windows environmental variables:

    ===============================  =====================================
    Windows Environmental Variables  Example path
    ===============================  =====================================
    ``%PROGRAMFILES%``               ``C:\\Program Files``
    ``%PROGRAMFILES(X86)%``          ``C:\\Program Files (x86)``
    ``%USERPROFILE%``                ``C:\\Users\\john``
    ``%APPDATA%``                    ``C:\\Users\\john\\AppData\\Roaming``
    ``%LOCALAPPDATA%``               ``C:\\Users\\john\\AppData\\Local``
    ===============================  =====================================

    When :py:mod:`ffmpegio` is first imported in Python, it automatically run
    this function once, searching in the system path and Windows default
    locations (see above). If both ffmpeg and ffprobe are not found, a
    warning message is displayed.

    """

    global FFMPEG_BIN, FFPROBE_BIN

    ext = ".exe" if _os.name == "nt" else ""

    dirs = [dir] if dir else [""]

    if not dir and _os.name == "nt":
        dirs.extend(
            [
                _os.path.join(d, "ffmpeg", "bin")
                for d in [
                    *[
                        _os.environ[var]
                        for var in (
                            "PROGRAMFILES",
                            "PROGRAMFILES(X86)",
                            "USERPROFILE",
                            "APPDATA",
                            "LOCALAPPDATA",
                        )
                        if var in _os.environ
                    ],
                    *[
                        _os.path.join(_os.environ[var], "Programs")
                        for var in (
                            "APPDATA",
                            "LOCALAPPDATA",
                        )
                        if var in _os.environ
                    ],
                ]
            ]
        )

    def search(cmd):
        for d in dirs:
            p = _shutil.which(_os.path.join(d, cmd + ext))
            if p:
                return p
        return None

    p = search("ffmpeg")
    if not p:
        raise Exception(
            "ffmpeg binary not found. Install ffmpeg & ffprobe and add their directory to the path first."
        )

    pp = search("ffprobe")
    if not pp:
        raise Exception(
            "only ffmpeg binary found and ffprobe missing. Make sure both ffmpeg and ffprobe are available on the same directory."
        )

    FFMPEG_BIN = p
    FFPROBE_BIN = pp


# initialize the paths
try:
    find()
except Exception as e:
    _logging.warn(str(e))


def _get_ffmpeg(probe=False):

    path = FFPROBE_BIN if probe else FFMPEG_BIN

    if not path:
        raise Exception(
            "FFmpeg executables not found. Run `ffmpegio.set_path()` first or place FFmpeg executables in auto-detectable path locations."
        )

    return path


###############################################################################


def ffprobe(
    args,
    *sp_arg,
    stdout=PIPE,
    stderr=PIPE,
    universal_newlines=True,
    encoding="utf8",
    hide_banner=True,
    **sp_kwargs,
):
    """run ffprobe command as a subprocess (blocking)

    :param args: ffprobe argument options
    :type args: seq or str
    :param hide_banner: False to output ffmpeg banner, defaults to True
    :type hide_banner: bool, optional
    :return: ffprobe stdout output
    :rtype: str
    """
    args = [
        _get_ffmpeg(probe=True),
        *(["-hide_banner"] if hide_banner else []),
        *(_shlex.split(args) if isinstance(args, str) else args),
    ]

    _logging.debug(form_shell_cmd(args))

    ret = _sp.run(
        args,
        *sp_arg,
        stdout=stdout,
        stderr=stderr,
        universal_newlines=universal_newlines,
        encoding=encoding,
        **sp_kwargs,
    )

    if ret.returncode != 0:
        raise Exception(f"execution failed\n   {form_shell_cmd(args)}\n\n{ret.stderr}")
    return ret.stdout


###############################################################################


def exec(
    ffmpeg_args,
    hide_banner=True,
    progress=None,
    overwrite=None,
    capture_log=None,
    stdin=None,
    stdout=None,
    stderr=None,
    sp_run=_sp.run,
    **sp_kwargs,
):
    """run ffmpeg command

    :param ffmpeg_args: FFmpeg argument options
    :type ffmpeg_args: dict, seq(str), or str
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :type hide_banner: bool, optional
    :param progress: progress monitor object, defaults to None
    :type progress: ProgressMonitorThread, optional
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param capture_log: True to capture log messages on stderr, False to suppress
                        console log messages, defaults to None (show on console)
    :type capture_log: bool or None, optional
    :param stdin: source file object, defaults to None
    :type stdin: readable file-like object, optional
    :param stdout: sink file object, defaults to None
    :type stdout: writable file-like object, optional
    :param stderr: file to log ffmpeg messages, defaults to None
    :type stderr: writable file-like object, optional
    :param sp_run: function to run FFmpeg as a subprocess, defaults to subprocess.run
    :type sp_run: Callable, optional
    :param **sp_kwargs: additional keyword arguments for sp_run, optional
    :type **sp_kwargs: dict
    :return: depends on sp_run
    :rtype: depends on sp_run
    """

    # convert to FFmpeg argument dict if str or seq(str) given
    if not isinstance(ffmpeg_args, dict):
        ffmpeg_args = parse(ffmpeg_args)

    gopts = ffmpeg_args.get("global_options", None)
    if hide_banner:
        if gopts is None:
            gopts = ffmpeg_args["global_options"] = {"hide_banner": None}
        else:
            gopts["hide_banner"] = None

    if progress and progress.url:
        if gopts is None:
            ffmpeg_args["global_options"] = {"progress": progress.url}
        else:
            gopts["progress"] = progress.url

    # configure stdin pipe (if needed)
    def isreadable(f):
        try:
            return f.fileno() and f.readable()
        except:
            return False

    inpipe = (
        next(
            (
                stdin if isreadable(stdin) else PIPE
                for inp in ffmpeg_args["inputs"]
                if inp[0] in ("-", "pipe:", "pipe:0")  # or not isinstance(inp[0], str)
            ),
            stdin,
        )
        if "inputs" in ffmpeg_args and 'input' not in sp_kwargs
        else stdin
    )

    if stdin is not None and inpipe != stdin:
        raise ValueError("FFmpeg expects to pipe in but stdin not specified")

    # configure stdout
    def iswritable(f):
        try:
            return f.fileno() and f.writable()
        except:
            return False

    outpipe = (
        next(
            (
                stdout if iswritable(stdout) else PIPE
                for outp in ffmpeg_args["outputs"]
                if outp[0] in ("-", "pipe:", "pipe:1")  # or not isinstance(inp[0], str)
            ),
            stdout,
        )
        if "outputs" in ffmpeg_args
        else stdout
    )

    if stdout is not None and outpipe != stdout:
        raise ValueError("FFmpeg expects to pipe out but stdin not specified")

    # set stderr for logging FFmpeg message
    if stderr == _sp.STDOUT and outpipe == PIPE:
        raise ValueError("stderr cannot be redirected to stdout, which is in use")
    errpipe = stderr or (
        PIPE if capture_log else None if capture_log is None else DEVNULL
    )

    # set y or n flags (overwrite)
    gopts = ffmpeg_args["global_options"]
    if not (gopts and ("y" in gopts or "n" in gopts)):
        if gopts is None:
            gopts = ffmpeg_args["global_options"] = {}
        if overwrite is not None:
            gopts["y" if overwrite else "n"] = None
        elif inpipe == PIPE:
            gopts["n"] = None

    args = compose(ffmpeg_args, command=_get_ffmpeg())
    _logging.debug(args)

    # run the FFmpeg
    return sp_run(args, stdin=inpipe, stdout=outpipe, stderr=errpipe, **sp_kwargs)


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
    s = exec(
        ["-version"],
        hide_banner=False,
        stdout=PIPE,
        universal_newlines=True,
        encoding="utf-8",
    ).stdout.splitlines()
    v = dict(version=_re.match(r"ffmpeg version (\S+)", s[0])[1])
    i = 2 if s[1].startswith("built with") else 1
    if s[i].startswith("configuration:"):
        v["configuration"] = sorted([m[1] for m in _re.finditer(r"\s--(\S+)", s[i])])
        i += 1
    lv = None
    for l in s[i:]:
        m = _re.match(r"(\S+)\s+(.+?) /", l)
        if m:
            if lv is None:
                lv = v["library_versions"] = {}
            lv[m[1]] = m[2].replace(" ", "")
    return v
