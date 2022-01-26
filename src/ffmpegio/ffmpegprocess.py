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

# from subprocess import (
#     DEVNULL,
#     PIPE,
#     TimeoutExpired,
#     # CalledProcessError,
#     # CompletedProcess,
# )

# PIPE_NONBLK = -4

from threading import Thread as _Thread
import subprocess as _sp
from subprocess import PIPE, DEVNULL
from .ffmpeg import exec, parse, ProgressMonitor
from .configure import move_global_options
from .utils import bytes_to_ndarray as _as_array

__all__ = ["run", "Popen", "PIPE", "DEVNULL"]


def monitor_process(
    proc, close_stdin=True, close_stdout=True, close_stderr=True, on_exit=None
):
    """thread function to monitor subprocess termination

    :param proc: subprocess to be monitored
    :type proc: subprocess.Popen
    :param close_stdin: if True, auto-close stdin, defaults to True
    :type close_stdin: bool, optional
    :param close_stdout: if True, auto-close stdout, defaults to True
    :type close_stdout: bool, optional
    :param close_stderr: if True, auto-close stderr, defaults to True
    :type close_stderr: bool, optional
    :param on_exit: callback function(s) to be called after process is terminated and
                    all auto-closing streams are closed
    :type on_exit: Callable or seq(Callables), optional
    """

    proc.wait()
    if close_stdin and proc.stdin:
        try:
            proc.stdin.close()
        except:
            pass
    if close_stdout and proc.stdout:
        try:
            proc.stdout.close()
        except:
            pass
    if close_stderr and proc.stderr:
        try:
            proc.stderr.close()
        except:
            pass
    if on_exit is not None:
        try:
            on_exit()
        except:
            for fcn in on_exit:
                fcn()


class Popen(_sp.Popen):
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
    :param close_stdin: True to auto-close stdin, defaults to None (True only if stdin not given)
    :type close_stdin: bool, optional
    :param close_stdout: True to auto-close stdout, defaults to None (True only if stdout not given)
    :type close_stdout: bool, optional
    :param close_stderr: True to auto-close stderr, defaults to None (True only if stderr not given)
    :type close_stderr: bool, optional
    :param on_exit: function(s) to execute when FFmpeg process terminates, defaults to None
    :type on_exit: Callable or seq(Callable), optional
    :param \\**other_popen_args: other keyword arguments to :py:class:`subprocess.Popen`
    :type \\**other_popen_args: dict, optional

    If :ref:`ffmpeg_args<adv_args>` calls for input or output to be piped (e.g., url="-") then :code:`Popen` creates
    a pipe for each piped url. If input is piped, :code:`stdin` is default to :code:`ffmpegio.io.QueuedWriter`
    class instance.  If output is piped, :code:`stdout` is default to :code:`ffmpegio.io.QueuedReader` class
    instance. If :code:`capture_log=True`, then :code:`stderr` is default to :code:`ffmpegio.io.QueuedWriter`. See
    :ref:`ffmpegio.io module<adv_io>` for how to use these custom stream classes.

    Alternately, a file-stream object could be specified in the argument for each of :code:`stdin`, :code:`stdout`,
    and :code:`stderr` to redirect pipes to existing file streams. If files aren't already open in Python,
    specify their urls in :ref:`ffmpeg_args<adv_args>` instead of using the pipes.

    """

    def __init__(
        self,
        ffmpeg_args,
        hide_banner=True,
        progress=None,
        overwrite=None,
        capture_log=None,
        stdin=None,
        stdout=None,
        stderr=None,
        close_stdin=None,
        close_stdout=None,
        close_stderr=None,
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
                    "bufsize", "executable",
                    "close_fds", "shell", "niversal_newlines", "pass_fds",
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
        self._progmon = None if progress is None else ProgressMonitor(progress)

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
            self._progmon.cancelfun = self.terminate
            self._progmon.start()

        # start the process monitor to perform the cleanup when FFmpeg terminates
        # if auto-close mode not set, audo-close only if stream handlers are not given
        if close_stdin is None:
            close_stdin = stdin is None
        if close_stdout is None:
            close_stdout = stdout is None
        if close_stderr is None:
            close_stderr = stderr is None
        if self._progmon:
            if on_exit:
                try:
                    on_exit = (self._progmon.join, *on_exit)
                except:
                    on_exit = (self._progmon.join, on_exit)
            else:
                on_exit = self._progmon.join

        self._monitor = _Thread(
            target=monitor_process,
            args=(self, close_stdin, close_stdout, close_stderr, on_exit),
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
        self._monitor.join()

    def kill(self):
        """Kill the FFmpeg process"""
        super().kill()
        self._monitor.join()

    def send_signal(self, sig: int):
        """Sends the signal signal to the FFmpeg process

        :param sig: signal id
        :type sig: int
        """
        try:
            super().send_signal(sig)
            if self.returncode is None:
                self._monitor.join()
        except:
            pass

    ####################################################################################################


def run(
    ffmpeg_args,
    hide_banner=True,
    progress=None,
    overwrite=None,
    capture_log=None,
    stdin=None,
    stdout=None,
    stderr=None,
    input=None,
    size=-1,
    shape=None,
    dtype=None,
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
    :param size: size of stdout items to read, default -1
    :type size: int, optional
    :param shape: shape of the output array elements,
        defaults to None (results in 1d array)
    :type shape: int or tuple of int, optional
    :param dtype: output array data type, defaults to None
    :type dtype: numpy data-type, optional
    :param \\**other_popen_kwargs: other keyword arguments of :py:class:`Popen`, defaults to {}
    :type \\**other_popen_kwargs: dict, optional
    :rparam: completed process
    :rtype: subprocess.CompleteProcess
    """

    with ProgressMonitor(progress) as progmon:
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
            input=input if input is None else memoryview(input).cast("b"),
            **other_popen_kwargs,
        )

    # format output
    if ret.stdout is not None:
        if shape is not None or dtype is not None:
            ret.stdout = _as_array(ret.stdout, shape, dtype)
        if size > 0:
            ret.stdout = ret.stdout[:size]

    # split log lines
    if ret.stderr is not None:
        ret.stderr = ret.stderr.decode("utf-8")

    return ret
