r"""FFmpeg subprocesses with accessible I/O streams
This module mimics Python's `subprocess` library module and allows you to
spawn FFmpeg processes, connect to their input/output/error pipes, and obtain
their return codes.

To read/write a media file, `run_simple()` is the fast and simple solution. Use
more complex `run()` if FFmpeg progress callback

Main API
========
run(...): Runs a FFmpeg command, waits for it to complete, then returns a
          CompletedProcess instance.
Popen(...): A subclass of subprocess.Popen to manage FFmpeg subprocess.

Constants
---------
DEVNULL: Special value that indicates that os.devnull should be used
PIPE:    Special value that indicates a pipe should be created

"""

from __future__ import annotations

import logging
import signal
import subprocess as sp
from collections import abc
from copy import deepcopy
from os import name as os_name
from os import path
from tempfile import TemporaryDirectory
from threading import Thread

from ._typing import (
    IO,
    Any,
    Callable,
    FFmpegOptionDict,
    Optional,
    ProgressCallable,
    Sequence,
    TypedDict,
)
from .path import DEVNULL, PIPE, TimeoutExpired, devnull, ffmpeg
from .threading import ProgressMonitorThread
from .utils import (
    FFmpegInputUrlComposite,
    FFmpegInputUrlNoPipe,
    FFmpegOutputUrlComposite,
    FFmpegOutputUrlNoPipe,
)
from .utils.parser import FLAG, compose, parse

logger = logging.getLogger("ffmpegio")


__all__ = [
    "run",
    "Popen",
    "FLAG",
    "PIPE",
    "DEVNULL",
    "devnull",
    "TimeoutExpired",
    "FFmpegArgs",
]


##############################
## ffmpegprocess argument dict
##############################

FFmpegInputOptionTuple = tuple[FFmpegInputUrlComposite, FFmpegOptionDict]
"""tuple pair of FFmpeg input url compatible objects and its option dict

Supported input url objects:

- `str`
- `os.Path`
- `urllib.UrlParseResult`
- `FFConcat`
- `FilterGraphObject`
- `IO` 
- `Buffer`
"""

FFmpegOutputOptionTuple = tuple[FFmpegOutputUrlComposite, FFmpegOptionDict]
"""tuple pair of FFmpeg output url compatible objects and its option dict

Supported output url objects:

- `str`
- `IO`
- `Buffer`
"""

FFmpegNoPipeInputOptionTuple = tuple[FFmpegInputUrlNoPipe, FFmpegOptionDict]
"""tuple pair of FFmpeg input non-pipe url compatible objects and its option dict

Supported input url objects:

- `str`
- `FFConcat`
- `FilterGraphObject`
"""

FFmpegNoPipeOutputOptionTuple = tuple[FFmpegOutputUrlNoPipe, FFmpegOptionDict]
"""tuple pair of FFmpeg output non-pipe url compatible objects and its option dict
"""


class FFmpegArgs(TypedDict):
    """FFmpeg arguments


    ==============  ===============
    key             description
    ==============  ===============
    inputs          list of input definitions (pairs of url and options)
    outputs         list of output definitions (pairs of url and options)
    global_options  FFmpeg global options
    ==============  ===============
    """

    inputs: list[FFmpegInputOptionTuple]
    """list of input definitions (pairs of url and options)"""
    outputs: list[FFmpegOutputOptionTuple]
    """list of output definitions (pairs of url and options)"""
    global_options: FFmpegOptionDict
    """FFmpeg global options"""


def move_global_options(args: FFmpegArgs) -> FFmpegArgs:
    """move global options from the output options dicts

    :param args: FFmpeg arguments
    :returns: FFmpeg arguments (the same object as the input)
    """

    from .caps import options

    _global_options = options("global", name_only=True)

    global_options = args.get("global_options", None) or {}

    # global options may be given as output options
    for _, inopts in args.get("inputs", ()):
        if inopts:
            for k in (*(k for k in inopts.keys() if k in _global_options),):
                global_options[k] = inopts.pop(k)
    for _, outopts in args.get("outputs", ()):
        if outopts:
            for k in (*(k for k in outopts.keys() if k in _global_options),):
                global_options[k] = outopts.pop(k)
    if len(global_options):
        args["global_options"] = global_options

    return args


def exec(
    ffmpeg_args: FFmpegArgs,
    hide_banner: Optional[bool] = True,
    progress: Optional[ProgressCallable] = None,
    overwrite: Optional[bool] = None,
    capture_log: Optional[bool] = None,
    stdin: Optional[IO] = None,
    stdout: Optional[IO] = None,
    stderr: Optional[IO] = None,
    sp_run: Optional[Callable] = sp.run,
    **sp_kwargs: dict[str, Any],
) -> Any:
    """run ffmpeg command

    :param ffmpeg_args: FFmpeg argument options
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :param progress: progress monitor object, defaults to None
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :param capture_log: True to capture log messages on stderr, False to suppress
                        console log messages, defaults to None (show on console)
    :param stdin: source file object, defaults to None
    :param stdout: sink file object, defaults to None
    :param stderr: file to log ffmpeg messages, defaults to None
    :param sp_run: function to run FFmpeg as a subprocess, defaults to subprocess.run
    :param sp_kwargs: additional keyword arguments for sp_run, optional
    :return: depends on sp_run
    """

    # convert to FFmpeg argument dict if str or seq(str) given
    if not isinstance(ffmpeg_args, dict):
        ffmpeg_args = parse(ffmpeg_args)

    gopts = ffmpeg_args.get("global_options", None)
    if gopts is None:
        gopts = ffmpeg_args["global_options"] = {}

    # disable user-interaction by default
    if "stdin" not in gopts:
        gopts["nostdin"] = FLAG

    # hide preamble by default
    if hide_banner:
        gopts["hide_banner"] = FLAG

    # add URL to dump progress status
    if progress and progress.url:
        gopts["progress"] = progress.url

    # set y or n flags (overwrite)
    if overwrite is not None:
        if "y" in gopts or "n" in gopts:
            raise ValueError(
                "Cannot set both the overwrite argument and a y/n global flag."
            )
        elif overwrite:
            gopts["y"] = FLAG
        else:
            gopts["n"] = FLAG

    # turn on hw decoder by default
    # def check_hwaccel(url, opts):
    #     if opts is None:
    #         opts = {"hwaccel": "auto"}
    #     elif "hwaccel" not in opts:
    #         opts["hwaccel"] = "auto"
    #     return url, opts

    # if "inputs" in ffmpeg_args:
    #     try:
    #         ffmpeg_args["inputs"] = [
    #             check_hwaccel(url, opts) for url, opts in ffmpeg_args["inputs"]
    #         ]
    #     except:
    #         pass

    # configure stdin pipe (if needed)
    def isreadable(f):
        try:
            return f.fileno() and f.readable()
        except AttributeError:
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
        if "inputs" in ffmpeg_args and "input" not in sp_kwargs
        else stdin
    )

    if stdin is not None and inpipe != stdin:
        raise ValueError("FFmpeg expects to pipe in but stdin not specified")

    # configure stdout
    def iswritable(f):
        try:
            return f == DEVNULL or (f.fileno() and f.writable())
        except AttributeError:
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
        raise ValueError("FFmpeg expects to pipe out but stdout not specified")

    # set stderr for logging FFmpeg message
    if stderr == sp.STDOUT and outpipe == PIPE:
        raise ValueError("stderr cannot be redirected to stdout, which is in use")
    errpipe = stderr or (
        PIPE if capture_log else None if capture_log is None else DEVNULL
    )

    args = compose(ffmpeg_args)

    # run the FFmpeg
    return ffmpeg(
        args, sp_run=sp_run, stdin=inpipe, stdout=outpipe, stderr=errpipe, **sp_kwargs
    )


OnExitCallable = Callable[[int], None]
"""Signature of the callback function to be assigned to `monitor_process()`"""


def monitor_process(
    proc: sp.Popen, on_exit: Optional[OnExitCallable | Sequence[OnExitCallable]] = None
):
    """thread function to monitor subprocess termination

    :param proc: subprocess to be monitored
    :param on_exit: callback function(s) to be called after process is terminated
        and all auto-closing streams are closed. The signature of a callback
        function is:

            on_exit(returncode:int)

    """

    logger.debug("[monitor] waiting for FFmpeg to terminate...")
    proc.wait()
    logger.debug("[monitor] FFmpeg terminated")
    if on_exit is not None:
        returncode = proc.returncode
        for fcn in on_exit:
            try:
                fcn(returncode)
            except Exception:
                pass
                # TODO - need to re-raise these exceptions?

        logger.debug("[monitor] executed all on_exit callbacks")


class Popen(sp.Popen):
    def __init__(
        self,
        ffmpeg_args: FFmpegArgs,
        *,
        hide_banner: Optional[bool] = True,
        progress: Optional[ProgressCallable] = None,
        overwrite: Optional[bool] = None,
        capture_log: Optional[bool] = None,
        stdin: Optional[IO] = None,
        stdout: Optional[IO] = None,
        stderr: Optional[IO] = None,
        on_exit: Optional[OnExitCallable | Sequence[OnExitCallable]] = None,
        **other_popen_args: dict[str, Any],
    ):
        """Execute FFmpeg in a new process.

        :param ffmpeg_args: FFmpeg arguments
        :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
        :param progress: progress callback function, defaults to None. This function
                        takes two arguments and may return True to terminate execution::

                            progress(data:dict, done:bool) -> bool|None

        :param overwrite: True to overwrite if output url exists, defaults to None
                        (auto-select)
        :param capture_log: True to capture log messages on stderr, False to send
                        logs to console, defaults to None (no show/capture)
        :param stdin: source file object, defaults to None
        :param stdout: sink file object, defaults to None
        :param stderr: file to log ffmpeg messages, defaults to None
        :param on_exit: function(s) to execute when FFmpeg process terminates, defaults to None
        :param other_popen_args: other keyword arguments to :py:class:`subprocess.Popen`

        If :ref:`ffmpeg_args<adv_args>` calls for input or output to be piped (e.g., url="-") then :code:`Popen`
        automatically sets `stdin=PIPE` or `stdout=PIPE`. Alternately, a file-stream object could be
        specified in the argument for each of :code:`stdin`, :code:`stdout`, and :code:`stderr`
        to redirect pipes to existing file streams. If files aren't already open in Python,
        specify their urls in :ref:`ffmpeg_args<adv_args>` instead of using the pipes.

        """
        if any(
            (
                k
                for k in other_popen_args.keys()
                if k
                in (
                    # fmt: off
                    "executable",
                    "close_fds",
                    "shell",
                    "niversal_newlines",
                    "pass_fds",
                    "encoding",
                    "errors",
                    "text",
                    "pipesize",
                    # fmt: on
                )
            )
        ):
            raise ValueError(
                "Input arguments contain protected subprocess.Popen keyword argument(s)."
            )

        #: dict: The FFmpeg args argument as it was passed to `Popen`
        self.ffmpeg_args = move_global_options(
            {**ffmpeg_args} if isinstance(ffmpeg_args, dict) else parse(ffmpeg_args)
        )

        # run progress monitor
        self._progmon = None if progress is None else ProgressMonitorThread(progress)
        self._monitor = None

        # start FFmpeg process
        exec(
            self.ffmpeg_args,
            hide_banner,
            self._progmon,
            overwrite,
            capture_log,
            stdin,
            stdout,
            stderr,
            super().__init__,
        )

        # set progress monitor's cancelfun to allow its callback to terminate the FFmpeg process
        if self._progmon:
            self._progmon.cancelfun = self.send_signal
            self._progmon.start()

        # start the process monitor to perform the cleanup when FFmpeg terminates
        if self._progmon or capture_log or on_exit:
            if on_exit is None:
                on_exit = []
            else:
                try:
                    on_exit = [*on_exit]
                except:
                    on_exit = [on_exit]

            if capture_log:
                on_exit.append(lambda _: self.stderr.close())

            if self._progmon:
                on_exit.append(lambda _: self._progmon.join())

            self._monitor = Thread(
                target=monitor_process,
                args=(self, on_exit),
            )
            self._monitor.start()

    def wait(self, timeout=None):
        """Wait for FFmpeg process to terminate; returns self.returncode

        :param timeout: optional timeout in seconds, defaults to None
        :type timeout: float, optional

        For FFmpeg to terminate autonomously, its stdin PIPE must be closed.

        If the process does not terminate after timeout seconds, raise a TimeoutExpired exception.
        It is safe to catch this exception and retry the wait.
        """
        super().wait(timeout)

        # Popen waits on monitor thread as well. Ignore "cannot join current thread" error when
        # monitor waits Popen
        try:
            self._monitor.join()
        except:
            pass

    def terminate(self):
        """Terminate the FFmpeg process"""
        super().terminate()

        if self.poll() is not None:
            try:
                self._monitor.join()
            except:
                pass

    def kill(self):
        """Kill the FFmpeg process"""
        super().kill()
        try:
            self._monitor.join()
        except:
            pass

    def send_signal(
        self, sig: Optional[int] = None, kill_monitor: Optional[bool] = False
    ):
        """Sends the signal signal to the FFmpeg process

        :param sig: signal id, default SIGINT (POSIX) / CTRL_C_EVENT (Windows)
        :param kill_monitor: True to kill the monitor thread, default False

        Without any argument, `send_signal()` will perform control-C to initiate
        soft-terminate FFmpeg. FFmpeg may output additional frames before exits.

        Note: Setting `kill_monitor=True` will block the caller thread until the
        FFmpeg terminates.

        """

        if sig is None:
            sig = signal.CTRL_C_EVENT if os_name == "nt" else signal.SIGINT

        super().send_signal(sig)
        if kill_monitor:
            try:
                self._monitor.join()
            except:
                pass

    ####################################################################################################


def run(
    ffmpeg_args: FFmpegArgs,
    *,
    hide_banner: Optional[bool] = True,
    progress: Optional[ProgressCallable] = None,
    overwrite: Optional[bool] = None,
    capture_log: Optional[bool] = None,
    stdin: Optional[IO] = None,
    stdout: Optional[IO] = None,
    stderr: Optional[IO] = None,
    input: Optional[bytes] = None,
    **other_popen_kwargs: dict[str, Any],
) -> sp.CompletedProcess:
    """run FFmpeg subprocess with standard pipes with a single transaction

    :param ffmpeg_args: FFmpeg argument options
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :param progress: progress callback function, defaults to None. This function
                     takes two arguments:

                        progress(data:dict, done:bool) -> None

    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :param capture_log: True to capture log messages on stderr, False to send
                        logs to console, defaults to None (no show/capture)
    :param stdin: source file object, defaults to None
    :param stdout: sink file object, defaults to None
    :param stderr: file to log ffmpeg messages, defaults to None
    :param input: input data buffer must be given if FFmpeg is configured to receive
                    data stream from Python. It must be bytes convertible to bytes.
    :param other_popen_kwargs: other keyword arguments of :py:class:`Popen`, defaults to {}
    :rparam: completed subprocess object
    """

    with ProgressMonitorThread(progress) as progmon:
        # run the FFmpeg
        ret = exec(
            move_global_options(ffmpeg_args),
            hide_banner,
            progmon,
            overwrite,
            capture_log,
            stdin if input is None else None,
            stdout,
            stderr,
            input=input if input is None else memoryview(input),
            **other_popen_kwargs,
        )

    # return stderr as str
    if isinstance(ret.stderr, bytes):
        ret.stderr = ret.stderr.decode("utf-8")

    return ret


def run_two_pass(
    ffmpeg_args: FFmpegArgs,
    *,
    pass1_omits: Optional[
        Sequence[str, Sequence[str], dict[int, Sequence[str]]]
    ] = None,
    pass1_extras: Optional[
        dict[str, str] | Sequence[dict[str, str]] | dict[int, dict[str, str]]
    ] = None,
    overwrite: Optional[bool] = None,
    stdin: Optional[IO] = None,
    **other_run_kwargs: dict[str, Any],
) -> sp.CompletedProcess:
    """run FFmpeg subprocess with standard pipes with a single transaction twice for 2-pass encoding

    :param ffmpeg_args: FFmpeg argument options
    :param pass1_omits: per-file list of output arguments to ignore in pass 1. If not applicable to every
                        output file, use a nested dict with int keys to specify which output,
                        defaults to None (remove 'c:a' or 'acodec').
    :param pass1_extras: per-file list of additional output arguments to include in pass 1. If it does
                         not apply to every output files, use a nested dict with int keys to specify
                         which output, defaults to None (add 'an' if `pass1_omits` also None)
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :type hide_banner: bool, optional
    :param progress: progress callback function, defaults to None. This function
                     takes two arguments:

                        progress(data:dict, done:bool) -> None

    :type progress: callable object, optional
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param capture_log: True to capture log messages on stderr, False to send
                        logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param stdin: source file object, defaults to None
    :type stdin: readable file-like object, optional
    :param stderr: file to log ffmpeg messages, defaults to None
    :type stderr: writable file-like object, optional
    :param input: input data buffer must be given if FFmpeg is configured to receive
                    data stream from Python. It must be bytes convertible to bytes.
    :type input: bytes-convertible object, optional
    :param other_popen_kwargs: other keyword arguments of :py:class:`Popen`, defaults to {}
    :type other_popen_kwargs: dict, optional
    :rparam: completed process
    """

    # TODO allow multiple stream 2-pass encoding
    # TODO add additional arguments to specify which output file
    # TODO add additional arguments to control which output option to be added or dropped during 1st pass

    from_stream = stdin is not None
    if from_stream:
        try:
            assert stdin.seekable()
        except:
            raise ValueError("stdin must be seekable")

    ffmpeg_args["outputs"] = list(ffmpeg_args["outputs"])

    # ref: https://trac.ffmpeg.org/wiki/Encode/H.264#twopass
    pass1_args = deepcopy(ffmpeg_args)

    if pass1_extras is None:
        pass1_extras = {} if pass1_omits is None else {"an": None}
    if pass1_omits is None:
        pass1_omits = ["c:a", "acodec"]

    nouts = len(pass1_args["outputs"])
    if (
        isinstance(pass1_omits, abc.Sequence)
        and len(pass1_omits)
        and type(pass1_omits[0]) == str
    ):
        pass1_omits = [pass1_omits] * nouts
    if isinstance(pass1_extras, abc.Mapping):
        pass1_extras = [pass1_extras] * nouts

    def mod_pass1_outopts(opts, omits, extras):
        opts = opts or {}
        opts["f"] = "null"
        opts["pass"] = 1

        def omit_opt(k):
            try:
                del opts[k]
            except:
                pass

        for k in omits:
            omit_opt(k)

        try:
            for k, v in extras.items():
                opts[k] = v
        except:
            pass

        return None, opts

    pass1_args["outputs"] = [
        mod_pass1_outopts(o[1], omits, extras)
        for o, omits, extras in zip(pass1_args["outputs"], pass1_omits, pass1_extras)
    ]
    pass1_opts = pass1_args["global_options"] = pass1_args["global_options"] or {}
    pass1_opts["y"] = None
    try:
        del pass1_opts["n"]
    except:
        pass

    def mod_pass2_outopts(url, opts):
        try:
            opts["pass"] = 2
            return url, opts
        except:
            return (url, {"pass": 2})

    ffmpeg_args["outputs"] = [mod_pass2_outopts(*o) for o in ffmpeg_args["outputs"]]

    with TemporaryDirectory() as tmpdir:
        if "passlogfile" not in ffmpeg_args["outputs"][0][1]:
            ffmpeg_args["outputs"][0][1]["passlogfile"] = pass1_args["outputs"][0][1][
                "passlogfile"
            ] = path.join(tmpdir, "ffmpeg2pass")

        if stdin is not None:
            pos = stdin.tell()

        ret = run(pass1_args, **other_run_kwargs)
        if not ret.returncode:
            if stdin is not None:
                stdin.seek(pos)

            ret = run(ffmpeg_args, overwrite=overwrite, **other_run_kwargs)

    # split log lines
    if isinstance(ret.stderr, bytes):
        ret.stderr = ret.stderr.decode("utf-8")

    return ret
