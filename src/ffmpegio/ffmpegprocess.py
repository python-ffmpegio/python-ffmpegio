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
Popen(...): A class to stream input and output data in and out of FFmpeg. It
            duck-types `subprocess.Popen` but uses the queued I/O in `ffmpegio.io` 
            module. 

Constants
---------
DEVNULL: Special value that indicates that os.devnull should be used
PIPE:    Special value that indicates a pipe should be created

"""

from subprocess import (
    DEVNULL,
    PIPE,
    TimeoutExpired,
    # CalledProcessError,
    # CompletedProcess,
)
import re as _re, os as _os, logging as _logging
from threading import Condition as _Condition, Thread as _Thread, Lock as _Lock
from time import time as _time, sleep as _sleep
from tempfile import TemporaryDirectory as _TemporaryDirectory
import subprocess as _sp

# import numpy as _np

from .ffmpeg import _run, _as_array, parse
from .io import (
    Full as _Full,
    QueuedWriter,
    QueuedReader,
    QueuedLogger,
    _split_logs,
)


class ProgressMonitor(_Thread):
    def __init__(self, callback, url=None, timeout=10e-3):
        self._td = None if url else _TemporaryDirectory()
        self.url = url or _os.path.join(self._td.name, "progress.txt")
        self._callback = callback
        self.timeout = timeout
        self._mutex = _Lock()
        self._status = 0  # >0 done, <0 canceled
        self._status_change = _Condition(self._mutex)
        super().__init__()

    @property
    def completed(self):
        with self._mutex:
            return self._status > 0

    @property
    def canceled(self):
        with self._mutex:
            return self._status < 0

    @property
    def running(self):
        with self._mutex:
            return not self._status

    def wait(self, timeout=None):
        with self._status_change:
            if not self._status:
                self._status_change.wait(timeout)
            return self._status < 0

    def join(self):
        with self._mutex:
            if not self._status:
                self._status = -1
        super().join()
        if self._td is not None:
            try:
                self._td.cleanup()
            except:
                pass
            self._td = None

    def run(self):
        url = self.url
        last_mtime = None

        def set_status(st):
            with self._mutex:
                self._status = st

        pattern = _re.compile(r"(.+)?=(.+)")
        done = False
        _logging.debug(f'[progress_monitor] monitoring "{url}"')

        while self.running and not _os.path.isfile(url):
            _sleep(self.timeout)

        _logging.debug("[progress_monitor] file found")
        d = {}
        with open(url, "rt") as f:
            while self.running:
                mtime = _os.fstat(f.fileno()).st_mtime
                if mtime != last_mtime:
                    lines = f.readlines()
                    last_mtime = mtime
                    for line in lines:
                        m = pattern.match(line)
                        if not m:
                            continue
                        if m[1] != "progress":
                            d[m[1]] = m[2]
                        else:
                            done = m[2] == "end"
                            if done:
                                set_status(1)
                            try:
                                if self._callback(d, done):
                                    _logging.debug(
                                        "[progress_monitor] operation canceled by user agent"
                                    )
                                    set_status(-1)
                            except Exception as e:
                                _logging.critical(
                                    f"[progress_monitor] user callback error:\n\n{e}"
                                )
                            d = {}
                            if not self.running:  # get out of the inner loop
                                break
                else:
                    _sleep(self.timeout)

        with self._status_change:
            self._status_change.notify_all()

        _logging.debug("[progress_monitor] terminated")


class Popen:
    def __init__(
        self,
        ffmpeg_args,
        hide_banner=True,
        progress=None,
        capture_log=None,
        input_queue_size=0,
        output_queue_size=0,
        output_block_size=2 ** 20,
        stdin=None,
        stdout=None,
        stderr=None,
        **popen_args,
    ):
        """Execute FFmpeg in a new process.

        :param ffmpeg_args: FFmpeg arguments
        :type ffmpeg_args: dict, seq, or str
        :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
        :type hide_banner: bool, optional
        :param progress: progress callback function, defaults to None
        :type progress: callable object, optional
        :param capture_log: True to capture log messages on stderr, False to send
                        logs to console, defaults to None (no show/capture)
        :type capture_log: bool, optional
        :param input_queue_size: maximum size of the stdin queue, default 0 (infinite)
        :type input_queue_size: int, optional
        :param output_queue_size: maximum size of the stdout queue, default 0 (infinite)
        :type output_queue_size: int, optional
        :param output_block_size: maximum number of bytes to get FFmpeg in one transaction, default 2**20
        :type output_block_size: int, optional
        :param stdin: source file object, defaults to None
        :type stdin: readable file object, optional
        :param stdout: sink file object, defaults to None
        :type stdout: writable file object, optional
        :param stderr: file to log ffmpeg messages, defaults to None
        :type stderr: writable file object, optional

        Details on `progress` argument: Function signature
           ```
           progress() -> bool
           ```
        """
        if any(
            (
                k
                for k in popen_args.keys()
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

        self.args = (
            {**ffmpeg_args} if isinstance(ffmpeg_args, dict) else parse(ffmpeg_args)
        )

        self._progress = ProgressMonitor(progress) if progress else None

        def get_file(file, args, Default, argname, st_kwargs):

            # scan args for '-' or file object
            m = (
                [(i, arg[0]) for i, arg in enumerate(args) if arg[0] in ("-", "pipe:")]
                if args is not None
                else []
            )
            if len(m) > 1:
                raise ValueError(f"cannot redirect more than one stream to {argname}.")

            redirect = bool(m)
            create = False

            if not redirect:
                # nothing to redirect
                file = DEVNULL
            else:
                create = not file or file == PIPE
                if create:
                    file = Default(**st_kwargs)

            return file, create, args

        self.stdin, self._own_stdin, self.args["inputs"] = get_file(
            stdin,
            self.args["inputs"],
            QueuedWriter,
            "stdin",
            {"queue_size": input_queue_size},
        )
        self.stdout, self._own_stdout, self.args["outputs"] = get_file(
            stdout,
            self.args["outputs"],
            QueuedReader,
            "stdout",
            {"queue_size": output_queue_size, "block_size": output_block_size},
        )
        self.stderr, self._own_stderr = (
            get_file(
                stderr,
                [("-", None)] if capture_log else None,
                QueuedLogger,
                "stderr",
                {},
            )[:2]
            if capture_log is not False
            else (None, False)
        )

        self.writable = isinstance(self.stdin, QueuedWriter)
        self.readable = isinstance(self.stdout, QueuedReader)
        self.loggable = isinstance(self.stderr, QueuedLogger)

        # start FFmpeg process
        self._proc = _run(
            _sp.Popen,
            self.args,
            progress=self._progress and self._progress.url,
            hide_banner=hide_banner,
            stdin=self.stdin,
            stdout=self.stdout,
            stderr=self.stderr,
        )

        # start the FFmpeg process monitoring thread
        if self._progress or self.readable or self.loggable:
            self._thread = (
                _Thread(target=self._run_cancelable)
                if self._progress
                else _Thread(target=self._run)
            )
            self._thread.start()
        else:
            self._thread = None

    def __del__(self):
        if self._proc.poll():
            self._proc.kill()
        if self._thread:
            self._thread.join()

    def _run(self):
        _logging.debug("[ffmpegprocess.Popen thread] started")
        self._proc.wait()
        _logging.debug("[ffmpegprocess.Popen thread] ffmpeg process exited")
        if self.readable:
            if self._own_stdout:
                _logging.debug(f"[ffmpegprocess.Popen thread] joining stdout (drained: {self.stdout.drained})")
                self.stdout._pipe.join()
                _logging.debug(f"[ffmpegprocess.Popen thread] joined stdout (drained: {self.stdout.drained})")
            self.stdout.mark_eof()
        if self.loggable:
            if self._own_stderr:
                self.stderr._pipe.join()
            self.stderr.mark_eof()
        _logging.debug(f"[ffmpegprocess.Popen thread] exiting")

    def _run_cancelable(self):
        proc = self._proc
        progress = self._progress
        timeout = 10e-3

        # self.writable and self.stdin.close,

        _logging.debug("starting ffmpegprocess.Popen thread (with progress monitoring)")
        progress.start()
        while proc.returncode is None and not progress.canceled:
            try:
                proc.wait(timeout)
                _logging.debug(f"proc.returncode={proc.returncode}")
            except TimeoutExpired:
                pass
        if progress.canceled:
            proc.terminate()
            if self.writable:
                self.stdin.close()
            if self._own_stdin:
                self.stdin._pipe.join()
        if self.readable:
            self.stdout.mark_eof()
            if self._own_stdout:
                self.stdout._pipe.join()
        if self.loggable:
            self.stderr.mark_eof()
            if self._own_stderr:
                self.stderr._pipe.join()
        progress.join()
        _logging.debug("exiting ffmpegprocess.Popen thread (with progress monitoring)")

    @property
    def canceled(self):
        return self._progress and self._progress.canceled

    def poll(self):
        """check if FFmpeg process has terminated

        :return: returncode if terminated else None
        :rtype: int or None
        """
        return self._proc.poll()

    def wait(self, timeout=None):
        """wait for FFmpeg process to termiante

        :param timeout: timeout in seconds, defaults to None
        :type timeout: float, optional
        :raises TimeoutExpired
        :return: returncode
        :rtype: int
        """
        if self._thread is None:
            self._proc.wait(timeout)
        else:
            self._thread.join(timeout)
        return self.returncode

    def communicate(
        self,
        input=None,
        timeout=None,
        copy=False,
        size=-1,
        shape=None,
        dtype=None,
    ):
        """Interact with FFmpeg process: Send data to stdin. Read data from stdout and
        stderr, until end-of-file is reached. Wait for process to terminate and set
        the returncode attribute.

        :param input: input data buffer must be given if FFmpeg is configured to receive
                      data stream from Python. It must be bytes convertible to bytes.
        :type input: bytes-like object, optional
        :param timeout: seconds to allow till FFmpeg process terminates, defaults to None
        :type timeout: float or None, optional
        :param copy: True to place a copy of the input data in buffer, default False
        :type copy: bool, optional
        :param size: size of stdout items to read, default -1
        :type size: int, optional
        :param shape: shape of the output array elements,
            defaults to None (results in 1d array)
        :type shape: int or tuple of int, optional
        :param dtype: output array data type, defaults to None
        :type dtype: numpy data-type, optional
        :raises TimeoutExpired: if the process does not terminate after timeout seconds.
                Catching this exception and retrying communication will not lose any output.
        :return: a tuple (output_data, stderr_data). The output_data will be bytes if
                   stdout was opened in bytes mode, else numpy.ndarray. The stderr_data
                   is a tuple of information lines that FFmpeg output to stderr.
        :rtype: tuple
        """

        tend = _time() + timeout if timeout else None
        if input:
            if not self.writable:
                raise ValueError("No input allowed. stdin not open or managed.")
            try:
                self.stdin.write(input, True, timeout, copy)  # one data packet then
                self.stdin.write(None, True, timeout)  # close the pipe
            except _Full:
                raise TimeoutExpired

        if timeout is not None:
            timeout = max(tend - _time(), 1e-3)

        # get the output/console messages
        output_data = (
            None
            if not self.readable
            else self.stdout.read(size, True, timeout)
            if shape is None and dtype is None
            else self.stdout.read_as_array(size, True, timeout, shape, dtype)
        )

        if timeout is not None:
            timeout = max(tend - _time(), 1e-3)

        # let FFmpeg run till terminates
        self.wait(timeout)

        if self.canceled:
            raise RuntimeError("User-agent canceled the FFmpeg execution")

        stderr_data = self.stderr.readlines(-1, False) if self.loggable else None

        return output_data, stderr_data

    def terminate(self):
        try:
            self._proc.terminate()
        except ProcessLookupError:
            pass
        if self._thread:
            self._thread.join()

    def kill(self):
        try:
            self._proc.kill()
        except ProcessLookupError:
            pass
        if self._thread:
            self._thread.join()

    @property
    def pid(self):
        return self._proc.pid

    @property
    def returncode(self):
        return self._proc.returncode

    ####################################################################################################


def run(
    ffmpeg_args,
    hide_banner=True,
    progress=None,
    capture_log=None,
    stdin=None,
    stdout=None,
    stderr=None,
    input=None,
    size=-1,
    shape=None,
    dtype=None,
    **kwargs,
):
    """run FFmpeg subprocess with standard pipes with a single transaction

    :param ffmpeg_args: FFmpeg argument options
    :type ffmpeg_args: dict, seq, or str
    :param hide_banner: False to output ffmpeg banner in stderr, defaults to True
    :type hide_banner: bool, optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param capture_log: True to capture log messages on stderr, False to send
                        logs to console, defaults to None (no show/capture)
    :type capture_log: bool, optional
    :param stdin: source file object, defaults to None
    :type stdin: readable file object, optional
    :param stdout: sink file object, defaults to None
    :type stdout: writable file object, optional
    :param stderr: file to log ffmpeg messages, defaults to None
    :type stderr: writable file object, optional
    :param input: input data buffer must be given if FFmpeg is configured to receive
                    data stream from Python. It must be bytes convertible to bytes.
    :type input: bytes-convertible object, optional
    :param timeout: seconds to allow till FFmpeg process terminates, defaults to None
    :type timeout: float or None, optional
    :param size: size of stdout items to read, default -1
    :type size: int, optional
    :param shape: shape of the output array elements,
        defaults to None (results in 1d array)
    :type shape: int or tuple of int, optional
    :param dtype: output array data type, defaults to None
    :type dtype: numpy data-type, optional
    :rparam: completed process
    :rtype: subprocess.CompleteProcess
    """

    ffmpeg_args = (
        {**ffmpeg_args} if isinstance(ffmpeg_args, dict) else parse(ffmpeg_args)
    )

    # configure stdin pipe (if needed)
    inpipe = next(
        (
            PIPE
            for inp in ffmpeg_args["inputs"]
            if inp[0] in ("-", "pipe:", "pipe:0")  # or not isinstance(inp[0], str)
        ),
        DEVNULL,
    )

    if inpipe == PIPE:  # expects input
        if input is not None:
            if stdin is not None:
                raise ValueError("stdin and input arguments may not both be used")
            inpipe = None  # let sp.run handle stdin assignment
        elif stdin in (None, DEVNULL, PIPE):
            raise ValueError("FFmpeg expects input pipe but no input given")
        else:
            inpipe = stdin  # redirection
    elif stdin == PIPE or input is not None:
        raise ValueError(
            "FFmpeg does not expect input pipe but stdin==PIPE or input is given"
        )

    # configure stdout
    outpipe = (
        stdout
        if stdout is not None
        else next(
            (
                PIPE
                for inp in ffmpeg_args["outputs"]
                if inp[0] in ("-", "pipe:", "pipe:1")  # or not isinstance(inp[0], str)
            ),
            DEVNULL,
        )
    )

    # set stderr for logging FFmpeg message
    if stderr == _sp.STDOUT:
        raise ValueError("stderr cannot be redirected to stdout")
    errpipe = stderr or (
        PIPE if capture_log else DEVNULL if capture_log is None else None
    )

    pmon = progress and ProgressMonitor(progress)
    if pmon:
        pmon.start()

    try:
        # run the FFmpeg
        ret = _run(
            _sp.run,
            ffmpeg_args,
            hide_banner=hide_banner,
            progress=pmon and pmon.url,
            stdout=outpipe,
            stderr=errpipe,
            **(
                {"input": memoryview(input).cast("b")}
                if inpipe is None
                else {"stdin": inpipe}
            ),
            **kwargs,
        )
    finally:
        if pmon:
            pmon.wait(1)
            pmon.join()

    # format output
    if ret.stdout is not None:
        if shape is not None or dtype is not None:
            ret.stdout = _as_array(ret.stdout, shape, dtype)
        if size > 0:
            ret.stdout = ret.stdout[:size]

    # split log lines
    if ret.stderr is not None:
        ret.stderr = _split_logs(ret.stderr)

    return ret

    # equivalent if ffmpegprocess.Popen is used (slower)
    # ===========================================================================
    # proc = Popen(*popen_args, input_copy=False, **kwargs)

    # if isinstance(proc.stdin, QueuedWriter) and input is None:
    #     raise ValueError(
    #         "`input` argument is required as an input is expected from memory."
    #     )

    # output_data, stderr_data = proc.communicate(
    #     input, timeout, copy, size, shape, dtype
    # )

    # if check and proc.returncode:
    #     raise CalledProcessError

    # return CompletedProcess(
    #     proc.args, proc.returncode, stdout=output_data, stderr=stderr_data
    # )
