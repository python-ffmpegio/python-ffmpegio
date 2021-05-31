import shlex, re, os, shutil, logging
import threading, io, time, tempfile
import subprocess as sp
from collections import abc
from . import filter_utils

PIPE = sp.PIPE

form_shell_cmd = (
    shlex.join
    if hasattr(shlex, "join")
    else lambda args: " ".join(shlex.quote(arg) for arg in args)
)

# list of global options (gathered on 4/9/21)
_global_options = (
    ("-y", 0),
    ("-n", 0),
    ("-cpuflags", 1),
    ("-stats", 0),
    ("-stats_period", 0),
    ("-progress", 1),
    ("-debug_ts", 0),
    ("-qphist", 0),
    ("-benchmark", 0),
    ("-benchmark_all", 0),
    ("-timelimit", 1),
    ("-dump", 0),
    ("-hex", 0),
    ("-filter_complex", 1),
    ("-filter_threads", 1),
    ("-lavfi", 1),
    ("-filter_complex_script", 1),
    ("-sdp_file", 1),
    ("-abort_on", 1),
    ("-max_error_rate", 0),
    ("-xerror", 0),
    ("-auto_conversion_filters", 0),
)

_output_flags = ("-dn", "-an", "-vn", "-copyinkf", "-sn", "-bitexact", "-shortest")


def parse_options(args):
    """parse command-line option arguments

    :param args: argument string or sequence of arguments
    :type args: str or seq of str
    :return: parsed options. Flag options get None as their values.
    :rtype: dict
    """
    if isinstance(args, str):
        args = shlex.split(args)
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
    :type cmdline: str
    :return: ffmpegio FFmpeg argument dict
    :rtype: dict
    """

    # remove multi-line command
    cmdline = re.sub(r"\\\n", " ", cmdline)

    # split the command line into its options
    args = shlex.split(cmdline)

    # exclude 'ffmpeg' command if present
    if re.search(r'(?:^|[/\\])?ffmpeg(?:.exe)?"?$', args[0], re.IGNORECASE):
        args = args[1:]

    # identify -i options
    ipos = [i for i, v in enumerate(args) if v == "-i"]
    ninputs = len(ipos)
    inputs = [None] * ninputs
    if ninputs:
        i0 = 0
        for j in range(ninputs):
            i = ipos[j]
            inputs[j] = (args[i + 1], parse_options(args[i0:i]))
            i0 = i + 2
        args = args[i0:]  # drop all input arguments

    # identify output_urls
    nargs = len(args)
    opos = (
        [
            i
            for i in range(1, nargs)
            if args[i][0] != "-"
            and (args[i - 1][0] != "-" or args[i - 1].split(":")[0] in _output_flags)
        ]
        if nargs > 1
        else [0]
        if nargs > 0
        else []
    )

    noutputs = len(opos)
    outputs = [None] * noutputs
    if noutputs:
        i0 = 0
        for j in range(noutputs):
            i = opos[j]
            outputs[j] = (args[i], parse_options(args[i0:i]))
            i0 = i + 1
        args = args[i0:]  # drop all input arguments

    # identify and transfer global options
    gopts = {}
    gnames = [o[0][1:] for o in _global_options]

    def extract_gopts(configs):
        for cfg in configs:
            d = cfg[1]
            keys = [key for key in d.keys() if key in gnames]
            for key in keys:
                gopts[key] = d.pop(key)

    extract_gopts(inputs)
    extract_gopts(outputs)

    return dict(_global_options=gopts, inputs=inputs, outputs=outputs)


def compose(global_options={}, inputs=[], outputs=[], command="", shell_command=False):
    """compose ffmpeg subprocess arguments from argument dict values

    :param _global_options: global options, defaults to {}
    :type _global_options: dict, optional
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
    """

    def opts2args(opts):
        args = []
        for key, val in opts.items():
            if (
                (key == "vf" or key == "af" or key == "filter_complex")
                and val is not None
                and not isinstance(val, str)
            ):
                val = (
                    filter_utils.compose_graph(*val[:-1], **val[-1])
                    if isinstance(val[-1], dict)
                    else filter_utils.compose_graph(*val)
                )

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
                args.extend(opts2args(opts))
            args.extend(["-i", url])
        return args

    def outputs2args(outputs):
        args = []
        for url, opts in outputs:
            if opts:
                args.extend(opts2args(opts))
            args.append(url)
        return args

    args = [
        *([command] if command else []),
        *opts2args(global_options or {}),
        *inputs2args(inputs),
        *outputs2args(outputs),
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
    return os.path.dirname(FFMPEG_BIN) if found() else None


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
    locations (see below). If both not found, a warning message is displayed.

    """

    global FFMPEG_BIN, FFPROBE_BIN

    ext = ".exe" if os.name == "nt" else ""

    dirs = [dir] if dir else [""]

    if not dir and os.name == "nt":
        dirs.extend(
            [
                os.path.join(d, "ffmpeg", "bin")
                for d in [
                    *[
                        os.environ[var]
                        for var in (
                            "PROGRAMFILES",
                            "PROGRAMFILES(X86)",
                            "USERPROFILE",
                            "APPDATA",
                            "LOCALAPPDATA",
                        )
                        if var in os.environ
                    ],
                    *[
                        os.path.join(os.environ[var], "Programs")
                        for var in (
                            "APPDATA",
                            "LOCALAPPDATA",
                        )
                        if var in os.environ
                    ],
                ]
            ]
        )

    def search(cmd):
        for d in dirs:
            p = shutil.which(os.path.join(d, cmd + ext))
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
    logging.warn(str(e))


def _get_ffmpeg(probe=False):

    path = FFPROBE_BIN if probe else FFMPEG_BIN

    if not path:
        raise Exception(
            "FFmpeg executables not found. Run `ffmpegio.set_path()` first or place FFmpeg executables in auto-detectable path locations."
        )

    return path


def run_sync(
    ffmpeg_args,
    *sp_arg,
    hide_banner=True,
    stdout=PIPE,
    stderr=PIPE,
    **sp_kwargs,
):
    """run ffmpeg command as a subprocess (blocking)

    :param ffmpeg_args: FFmpeg argument options
    :type ffmpeg_args: dict, seq, or str
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :type hide_banner: bool, optional
    :return: log of the completed FFmpeg run
    :rtype: str
    """
    if isinstance(ffmpeg_args, dict):
        ffmpeg_args = compose(**ffmpeg_args, command=_get_ffmpeg())
    else:
        ffmpeg_args = [
            _get_ffmpeg(),
            *(
                shlex.split(ffmpeg_args)
                if isinstance(ffmpeg_args, str)
                else ffmpeg_args
            ),
        ]

    if hide_banner:
        ffmpeg_args.insert(1, "-hide_banner")

    logging.debug(ffmpeg_args)

    ret = sp.run(ffmpeg_args, *sp_arg, stdout=stdout, stderr=stderr, **sp_kwargs)
    if ret.returncode != 0 and ret.stderr is not None:
        msg = ret.stderr
        try:
            msg = msg.decode("utf-8")
        finally:
            raise Exception(
                f"execution failed\n   {form_shell_cmd(ffmpeg_args)}\n\n{msg}"
            )

    return ret.stderr if ret.stdout is None else ret.stdout


def run(
    ffmpeg_args,
    *sp_arg,
    progress=None,
    hide_banner=True,
    stdout=PIPE,
    stderr=PIPE,
    **sp_kwargs,
):
    """start FFmpeg subprocess (non-blocking)

    :param ffmpeg_args: FFmpeg argument options
    :type ffmpeg_args: dict, seq, or str
    :param progress: progress callback function, defaults to None
    :type progress: function, optional
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :type hide_banner: bool, optional
    :return: Python subprocess Popen object to monitor/interact with the FFmpeg process
    :rtype: subprocess.Popen
    """
    if isinstance(ffmpeg_args, dict):
        ffmpeg_args = compose(**ffmpeg_args, command=_get_ffmpeg())
    else:
        ffmpeg_args = [
            _get_ffmpeg(),
            *(
                shlex.split(ffmpeg_args)
                if isinstance(ffmpeg_args, str)
                else ffmpeg_args
            ),
        ]

    if hide_banner:
        ffmpeg_args.insert(1, "-hide_banner")

    if progress:
        progress_monitor = _ProgressMonitor(progress)
        ffmpeg_args = [
            *ffmpeg_args[:1],
            "-progress",
            progress_monitor.url,
            *ffmpeg_args[1:],
        ]

    logging.debug(form_shell_cmd(ffmpeg_args))

    proc = sp.Popen(ffmpeg_args, *sp_arg, stdout=stdout, stderr=stderr, **sp_kwargs)

    # stderr_monitor = _StderrMonitor(proc)
    # stderr_monitor.start()

    if progress:
        progress_monitor.proc = proc
        progress_monitor.start()

    return proc


def ffprobe(
    args,
    *sp_arg,
    stdout=sp.PIPE,
    stderr=sp.PIPE,
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
        *(shlex.split(args) if isinstance(args, str) else args),
    ]

    logging.debug(form_shell_cmd(args))

    ret = sp.run(
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
    s = run_sync(
        ["-version"],
        hide_banner=False,
        stdout=sp.PIPE,
        universal_newlines=True,
        encoding="utf-8",
    ).splitlines()
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


class _ProgressMonitor(threading.Thread):
    def __init__(self, callback, initial_wait=0.5):
        threading.Thread.__init__(self)
        self._td = tempfile.TemporaryDirectory()
        self.url = os.path.join(self._td.name, "progress.txt")
        self.callback = callback
        self.initial_wait = initial_wait
        self.proc = None

    def run(self):
        proc = self.proc
        url = self.url
        callback = self.callback

        def readnext(f):
            txt = f.readline()
            m = pattern.match(txt)
            while not m:
                txt = f.readline()
                m = pattern.match(txt)
            return m

        pattern = re.compile(r"(.+)?=(.+)\n")
        done = False
        logging.debug(f'[progress_monitor] monitoring "{url}"')
        time.sleep(self.initial_wait)
        if proc.poll() is None and os.path.isfile(url):
            logging.debug(f"[progress_monitor] file found")
            with open(url, "rt") as f:
                while proc.poll() is None and not done:
                    d = {}
                    m = readnext(f)
                    while m[1] != "progress":
                        d[m[1]] = m[2]
                        m = readnext(f)
                    done = m[2] == "end"
                    if callback(d, done):
                        proc.terminate()
                        proc.stderr.write("Operation canceled by user agent")

        self._td.cleanup()


class _StderrMonitorIO(io.StringIO):
    def __init__(self):
        io.StringIO.__init__(self)
        self.lock = threading.Lock()

    def read(self, size=-1):
        self.lock.acquire()
        v = io.StringIO.read(self, size)
        self.lock.release()
        return v

    def readline(self, size=-1):
        self.lock.acquire()
        v = io.StringIO.readline(self, size)
        self.lock.release()
        return v

    def write(self, s):
        self.lock.acquire()
        pos = io.StringIO.tell(self)
        n = io.StringIO.write(self, s)
        io.StringIO.seek(self, pos)
        self.lock.release()
        return n

    def seek(self, offset, whence=io.SEEK_SET):
        self.lock.acquire()
        pos = io.StringIO.seek(self, offset, whence)
        self.lock.release()
        return pos

    def tell(self):
        self.lock.acquire()
        pos = io.StringIO.tell(self)
        self.lock.release()
        return pos


class _StderrMonitor(threading.Thread):
    def __init__(self, proc):
        threading.Thread.__init__(self)
        self.proc = proc
        self.input = proc.stderr
        self.output = _StderrMonitorIO()
        self.monitoring = True
        setattr(proc, "stderr", self.output)

        self.error_message = None
        proc._stderr_monitor = self

        def get_errmsg():
            if self.proc.returncode != 0:
                while self.monitoring:
                    time.sleep(0.05)
                txt = self.output.getvalue().splitlines()
                self.error_message = txt[-1]
            return self.error_message

        setattr(proc, "get_errmsg", get_errmsg)

    def run(self):
        proc = self.proc
        input = self.input

        if input is None:
            return

        def read_next():
            txt = input.readline().decode("utf-8")
            if txt and txt != "\n":
                self.output.write(txt)
            return txt

        while proc.poll() is None:
            read_next()

        while read_next():
            pass

        self.monitoring = False
