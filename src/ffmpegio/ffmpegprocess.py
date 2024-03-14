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

from collections import abc
from os import path, name as os_name
from threading import Thread
import subprocess as sp
from copy import deepcopy
from tempfile import TemporaryDirectory
import logging
import signal

logger = logging.getLogger("ffmpegio")

from .utils.parser import parse, compose, FLAG
from .threading import ProgressMonitorThread
from .configure import move_global_options
from .path import ffmpeg, DEVNULL, PIPE, devnull

__all__ = ["versions", "run", "Popen", "FLAG", "PIPE", "DEVNULL", "devnull"]


def exec(
    ffmpeg_args,
    hide_banner=True,
    progress=None,
    overwrite=None,
    capture_log=None,
    stdin=None,
    stdout=None,
    stderr=None,
    sp_run=sp.run,
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
        if "inputs" in ffmpeg_args and "input" not in sp_kwargs
        else stdin
    )

    if stdin is not None and inpipe != stdin:
        raise ValueError("FFmpeg expects to pipe in but stdin not specified")

    # configure stdout
    def iswritable(f):
        try:
            return f == DEVNULL or (f.fileno() and f.writable())
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


def monitor_process(proc, on_exit=None):
    """thread function to monitor subprocess termination

    :param proc: subprocess to be monitored
    :type proc: subprocess.Popen
    :param on_exit: callback function(s) to be called after process is terminated and
                    all auto-closing streams are closed
    :type on_exit: Callable or seq(Callables), optional

        on_exit(returncode)

    """

    logger.debug("[monitor] waiting for FFmpeg to terminate...")
    proc.wait()
    logger.debug("[monitor] FFmpeg terminated")
    if on_exit is not None:
        returncode = proc.returncode
        for fcn in on_exit:
            fcn(returncode)
        logger.debug("[monitor] executed all on_exit callbacks")


class Popen(sp.Popen):
    """Execute FFmpeg in a new process.

    :param ffmpeg_args: FFmpeg arguments
    :type ffmpeg_args: dict
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :type hide_banner: bool, optional
    :param progress: progress callback function, defaults to None. This function
                     takes two arguments and may return True to terminate execution::

                        progress(data:dict, done:bool) -> bool|None

    :type progress: Callable, optional
    :param overwrite: True to overwrite if output url exists, defaults to None
                      (auto-select)
    :type overwrite: bool, optional
    :param capture_log: True to capture log messages on stderr, False to send
                    logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param stdin: source file object, defaults to None
    :type stdin: readable file object, optional
    :param stdout: sink file object, defaults to None
    :type stdout: writable file object, optional
    :param stderr: file to log ffmpeg messages, defaults to None
    :type stderr: writable file object, optional
    :param on_exit: function(s) to execute when FFmpeg process terminates, defaults to None
    :type on_exit: Callable or seq(Callable), optional
    :param \\**other_popen_args: other keyword arguments to :py:class:`subprocess.Popen`
    :type \\**other_popen_args: dict, optional

    If :ref:`ffmpeg_args<adv_args>` calls for input or output to be piped (e.g., url="-") then :code:`Popen`
    automatically sets `stdin=PIPE` or `stdout=PIPE`. Alternately, a file-stream object could be
    specified in the argument for each of :code:`stdin`, :code:`stdout`, and :code:`stderr`
    to redirect pipes to existing file streams. If files aren't already open in Python,
    specify their urls in :ref:`ffmpeg_args<adv_args>` instead of using the pipes.

    """

    def __init__(
        self,
        ffmpeg_args,
        *,
        hide_banner=True,
        progress=None,
        overwrite=None,
        capture_log=None,
        stdin=None,
        stdout=None,
        stderr=None,
        on_exit=None,
        **other_popen_args,
    ):
        if any(
            (
                k
                for k in other_popen_args.keys()
                if k
                in (
                    # fmt: off
                    "executable", "close_fds", "shell", "niversal_newlines", "pass_fds",
                    "encoding", "errors", "text", "pipesize",
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

    def send_signal(self, sig: int = None, kill_monitor: bool = False):
        """Sends the signal signal to the FFmpeg process

        :param sig: signal id, default SIGINT (POSIX) / CTRL_C_EVENT (Windows)
        :type sig: int, optional
        :param kill_monitor: True to kill the monitor thread, default False
        :type kill_monitor: bool, optional

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
    ffmpeg_args,
    *,
    hide_banner=True,
    progress=None,
    overwrite=None,
    capture_log=None,
    stdin=None,
    stdout=None,
    stderr=None,
    input=None,
    **other_popen_kwargs,
):
    """run FFmpeg subprocess with standard pipes with a single transaction

    :param ffmpeg_args: FFmpeg argument options
    :type ffmpeg_args: dict
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
    :param stdout: sink file object, defaults to None
    :type stdout: writable file-like object, optional
    :param stderr: file to log ffmpeg messages, defaults to None
    :type stderr: writable file-like object, optional
    :param input: input data buffer must be given if FFmpeg is configured to receive
                    data stream from Python. It must be bytes convertible to bytes.
    :type input: bytes-convertible object, optional
    :param \\**other_popen_kwargs: other keyword arguments of :py:class:`Popen`, defaults to {}
    :type \\**other_popen_kwargs: dict, optional
    :rparam: completed process
    :rtype: subprocess.CompleteProcess
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
    ffmpeg_args,
    pass1_omits=None,
    pass1_extras=None,
    overwrite=None,
    stdin=None,
    **other_run_kwargs,
):
    """run FFmpeg subprocess with standard pipes with a single transaction twice for 2-pass encoding

    :param ffmpeg_args: FFmpeg argument options
    :type ffmpeg_args: dict
    :param pass1_omits: per-file list of output arguments to ignore in pass 1. If not applicable to every
                        output file, use a nested dict with int keys to specify which output,
                        defaults to None (remove 'c:a' or 'acodec').
    :type pass1_omits: seq(str) or seq(seq(str)) or dict(int:seq(str)) optional
    :param pass1_extras: per-file list of additional output arguments to include in pass 1. If it does
                         not apply to every output files, use a nested dict with int keys to specify
                         which output, defaults to None (add 'an' if `pass1_omits` also None)
    :type pass1_extras: dict(str) or seq(dict(str)) or dict(int:dict(str)), optional
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
    :param \\**other_popen_kwargs: other keyword arguments of :py:class:`Popen`, defaults to {}
    :type \\**other_popen_kwargs: dict, optional
    :rparam: completed process
    :rtype: subprocess.CompleteProcess
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
