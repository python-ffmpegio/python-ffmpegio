"""collection of thread classes for handling FFmpeg streams
"""

from copy import deepcopy
import re as _re, os as _os, logging as _logging
from threading import (
    Thread as _Thread,
    Condition as _Condition,
    Lock as _Lock,
    Event as _Event,
)
from io import TextIOBase as _TextIOBase, TextIOWrapper as _TextIOWrapper
from time import sleep as _sleep, time as _time
from tempfile import TemporaryDirectory as _TemporaryDirectory
from queue import Empty, Full, Queue as _Queue
import numpy as _np
from math import ceil

from .utils.avi import AviReader
from .utils.log import extract_output_stream as _extract_output_stream, FFmpegError
from .utils import bytes_to_ndarray as _as_array, get_itemsize as _get_itemsize


class ThreadNotActive(RuntimeError):
    pass


class ProgressMonitorThread(_Thread):
    """FFmpeg progress monitor class

    :param callback: [description]
    :type callback: function
    :param cancel_fun: [description], defaults to None
    :type cancel_fun: [type], optional
    :param url: [description], defaults to None
    :type url: [type], optional
    :param timeout: [description], defaults to 10e-3
    :type timeout: [type], optional
    """

    def __init__(self, callback, cancelfun=None, url=None, timeout=10e-3):
        if callback is None:
            self.url = self.cancelfun = self._thread = None
        else:
            tempdir = None if url else _TemporaryDirectory()
            self.url = url or _os.path.join(tempdir.name, "progress.txt")
            self.cancelfun = cancelfun
            super().__init__(args=(callback, tempdir, timeout))
            self._stop_monitor = _Event()

    def start(self):
        if self.url:
            super().start()

    def join(self, timeout=None):
        if self.url:
            self._stop_monitor.set()
            super().join(timeout)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.join()

    def run(self):
        callback, tempdir, timeout = self._args
        url = self.url

        pattern = _re.compile(r"(.+)?=(.+)")
        _logging.debug(f'[progress_monitor] monitoring "{url}"')

        while not (self._stop_monitor.is_set() or _os.path.isfile(url)):
            _sleep(timeout)

        _logging.debug("[progress_monitor] file found")

        if not self._stop_monitor.is_set():

            with open(url, "rt") as f:

                last_mtime = None

                def update(sleep=True):
                    d = {}
                    mtime = _os.fstat(f.fileno()).st_mtime
                    new_data = mtime != last_mtime
                    if new_data:
                        lines = f.readlines()
                        for line in lines:
                            m = pattern.match(line)
                            if not m:
                                continue
                            if m[1] != "progress":
                                val = m[2].lstrip()
                                try:
                                    val = int(val)
                                except:
                                    try:
                                        val = float(val)
                                    except:
                                        pass

                                d[m[1]] = val
                            else:
                                done = m[2] == "end"
                                try:
                                    if callback(d, done) and self.cancelfun:
                                        _logging.debug(
                                            "[progress_monitor] operation canceled by user agent"
                                        )
                                        self.cancelfun()
                                except Exception as e:
                                    _logging.critical(
                                        f"[progress_monitor] user callback error:\n\n{e}"
                                    )
                    elif sleep:
                        _sleep(timeout)

                while not self._stop_monitor.is_set():
                    last_mtime = update()

                # one final update just in case FFmpeg termianted during sleep
                update(False)

        if tempdir is not None:
            try:
                tempdir.cleanup()
            except:
                pass

        _logging.debug("[progress_monitor] terminated")


class LoggerThread(_Thread):
    def __init__(self, stderr, echo=False) -> None:
        self.stderr = stderr
        self.logs = []
        self._newline_mutex = _Lock()
        self.newline = _Condition(self._newline_mutex)
        self.echo = echo
        super().__init__()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stderr.close()
        self.join()  # will wait until stderr is closed
        return self

    def run(self):
        stderr = self.stderr
        if not isinstance(stderr, _TextIOBase):
            stderr = self.stderr = _TextIOWrapper(stderr, "utf-8")
        while True:
            try:
                log = stderr.readline()
            except:
                # stderr stream closed/FFmpeg terminated, end the thread as well
                break
            if not log and stderr.closed:
                break

            log = log[:-1]  # remove the newline

            if not log:
                _sleep(0.001)
                continue

            if self.echo:
                print(log)

            with self.newline:
                self.logs.append(log)
                self.newline.notify_all()

        with self.newline:
            self.stderr = None
            self.newline.notify_all()

    def index(self, prefix, start=None, block=True, timeout=None):
        start = int(start or 0)
        with self.newline:
            logs = self.logs[start:] if start else self.logs
            try:
                # check existing lines
                return (
                    next((i for i, log in enumerate(logs) if log.startswith(prefix)))
                    + start
                )
            except:
                if not self.is_alive():
                    raise ThreadNotActive("LoggerThread is not running")

                # no wait mode
                if not block:
                    raise ValueError("Specified line not found")

                # wait till matching line is read by the thread
                if timeout is not None:
                    timeout = _time() + timeout
                start = len(self.logs)
                while True:
                    tout = timeout and timeout - _time()
                    # wait till the next log update
                    if (tout is not None and tout < 0) or not self.newline.wait(tout):
                        raise TimeoutError("Specified line not found")

                    # FFmpeg could have been terminated without match
                    if self.stderr is None:
                        raise ValueError("Specified line not found")

                    # check the new lines
                    try:
                        return (
                            next(
                                (
                                    i
                                    for i, log in enumerate(self.logs[start:])
                                    if log.startswith(prefix)
                                )
                            )
                            + start
                        )
                    except:
                        # still no match, update the starting position
                        start = len(self.logs)

    def output_stream(self, file_id=0, stream_id=0, block=True, timeout=None):
        try:
            i = self.index(f"Output #{file_id}", block=block, timeout=timeout)
            self.index(f"  Stream #{file_id}:{stream_id}", i, block, timeout)
        except ThreadNotActive as e:
            raise e
        except TimeoutError:
            raise TimeoutError("Specified output stream not found")
        except Exception as e:
            raise ValueError("Specified output stream not found")

        with self._newline_mutex:
            return _extract_output_stream(self.logs, hint=i)

    @property
    def Exception(self):
        return FFmpegError(self.logs)


class ReaderThread(_Thread):
    def __init__(self, stdout, shape, dtype, nmin=None, queuesize=None):

        super().__init__()
        self.stdout = stdout  #:readable stream: data source
        self.shape = shape  #:tuple of ints: size of input item per sampled time
        self.dtype = dtype  #:numpy.dtype: data type of input item
        self.nmin = nmin  #:positive int: expected minimum number of read()'s n arg (not enforced)
        self.itemsize = None  #:int: number of bytes per time sample
        self._queue = _Queue(queuesize or 0)  # inter-thread data I/O
        self._carryover = None  # extra data that was not previously read by user
        self._collect = True

    def start(self):
        if self.shape is None or self.dtype is None:
            raise ValueError("Thread object's shape and dtype properties must be set")

        self.itemsize = _get_itemsize(self.shape, self.dtype)  # bytes/(frame-or-sample)
        super().start()

    def cool_down(self):

        # stop enqueue read samples
        self._collect = False
        try:
            self._queue.get_nowait()
        except:
            pass

    def join(self, timeout=None):
        if self._queue.full():
            if timeout:
                self._queue.not_full.wait(timeout)
                if self._queue.full():
                    return
            else:
                with self._queue.mutex:
                    self._queue.queue.clear()

        # if queue is full,
        super().join(timeout)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stdout.close()
        self.join()  # will wait until stdout is closed
        return self

    def run(self):
        shape = self.shape
        dtype = self.dtype
        blocksize = (
            self.nmin if self.nmin is not None else 1 if self.itemsize > 1024 else 1024
        ) * self.itemsize
        while True:
            try:
                data = self.stdout.read(blocksize)
            except:
                # stdout stream closed/FFmpeg terminated, end the thread as well
                break
            # print(f"reader thread: read {len(data)} bytes")
            if not data:
                if self.stdout.closed:  # just in case
                    break
                else:
                    break

            if self._collect:  # True until self.cooloff
                self._queue.put(_as_array(data, shape, dtype))
                # print(f"reader thread: queued samples")

    def read(self, n=-1, timeout=None):

        # wait till matching line is read by the thread
        block = self.is_alive() and n != 0
        if timeout is not None:
            timeout = _time() + timeout

        arrays = []
        n_new = max(n, -n)

        # grab any leftover data from previous read
        if self._carryover:
            arrays = [self._carryover]
            if n_new != 0:
                n_new -= self._carryover.shape[0]
            self._carryover = None

        # loop till enough data are collected
        nreads = 1 if n <= 0 else max(n_new, 0)
        nr = 0
        while True:
            tout = timeout and timeout - _time()
            if tout <= 0:
                break
            try:
                data = self._queue.get(block, tout)
                self._queue.task_done()
                arrays.append(data)
            except Empty:
                break

            nr += data.shape[0]
            if nr >= nreads:  # enough read
                if n < 0:
                    block = False  # keep reading until queue is empty
                else:
                    break

        # combine all the data and return requested amount
        if not len(arrays):
            return _np.empty((0, *self.shape))

        all_data = _np.concatenate(arrays)
        if n <= 0:
            return all_data
        if all_data.shape[0] > n:
            self._carryover = all_data[n:, ...]
        return all_data[:n, ...]

    def read_all(self, timeout=None):

        # wait till matching line is read by the thread
        if timeout is not None:
            timeout = _time() + timeout

        arrays = arrays = [self._carryover] if self._carryover else []
        self._carryover = None

        # loop till enough data are collected
        while not self.is_alive() or timeout and timeout > _time():
            try:
                data = self._queue.get(self.is_alive(), timeout and timeout - _time())
                self._queue.task_done()
                arrays.append(data)
            except Empty:
                break

        # combine all the data and return requested amount
        if not len(arrays):
            return _np.empty((0, *self.shape), self.dtype)

        return _np.concatenate(arrays)


class WriterThread(_Thread):
    """a thread to write byte data to a writable stream

    :param stdin: stream to write data to
    :type stdin: writable stream
    :param queuesize: depth of a queue for inter-thread data transfer, defaults to None
    :type queuesize: int, optional
    """

    def __init__(self, stdin, queuesize=None):
        super().__init__()
        self.stdin = stdin  #:writable stream: data sink
        self._queue = _Queue(queuesize or 0)  # inter-thread data I/O

    def join(self, timeout=None):

        # close the stream if not already closed
        self.stdin.close()

        # if empty, queue a dummy item to wake up the thread
        if self._queue.empty():
            self._queue.put(None)

        # if queue is full,
        super().join(timeout)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.join()  # will wait until stdout is closed
        return self

    def run(self):
        while True:
            # get next data block
            data = self._queue.get()
            self._queue.task_done()
            if data is None:
                break
            # print(f"writer thread: received {data.shape[0]} samples to write")
            try:
                nbytes = self.stdin.write(data)
                # print(f"writer thread: written {nbytes} written")
            except:
                # stdout stream closed/FFmpeg terminated, end the thread as well
                break
            if not nbytes and self.stdin.closed:  # just in case
                break

    def write(self, data, timeout=None):

        if not self.is_alive():
            raise ThreadNotActive("WriterThread is not running")

        data = self._queue.put(data, timeout)


class AviReaderThread(_Thread):
    def __init__(self, use_ya8=None, queuesize=None):

        super().__init__()
        self.reader = AviReader(use_ya8)  #:utils.avi.AviReader: AVI demuxer
        self.streams_ready = _Event()  #:Event: Set when received stream header info
        self.rates = None  # :dict(int:int|Fraction)
        self._queue = _Queue(queuesize or 0)  # inter-thread data I/O
        self._ids = None  #:dict(int:int): stream indices
        self._nread = None  #:dict(int:int): number of samples read/stream
        self._carryover = (
            None  #:dict(int:ndarray) extra data that was not previously read by user
        )

    @property
    def streams(self):
        return self.reader.streams if self.streams_ready else None

    def start(self, stdout):
        self._args = (stdout,)
        super().start()

    def join(self, timeout=None):
        # if queue is full,
        super().join(timeout)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.join()  # will wait until stdout is closed
        return self

    def run(self):

        reader = self.reader

        try:
            # start the AVI reader to process stdout byte stream
            reader.start(self._args[0])

            # initialize the stream properties
            self._ids = ids = [i for i in reader.streams]
            self._nread = {k: 0 for k in ids}
            self.rates = {
                k: v["frame_rate"] if v["type"] == "v" else v["sample_rate"]
                for k, v in reader.streams.items()
            }
        except:
            return
        finally:
            self.streams_ready.set()

        reader = self.reader
        for id, data in reader:
            self._queue.put((id, data))
        self._queue.put(None)  # end of stream

    def wait(self, timeout=None):
        return self.is_alive() and self.streams_ready.wait(timeout)

    def readchunk(self, timeout=None):
        """read the next avi chunk

        :param timeout: timeout in seconds, defaults to None (waits indefinitely)
        :type timeout: float, optional
        :raises TimeoutError: if terminated due to timeout
        :return: tuple of stream specifier and data array
        :rtype: (str, numpy.ndarray)
        """

        # wait till matching line is read by the thread
        tend = timeout and _time() + timeout

        # if stream header not received in time, raise error
        if not self.wait(timeout):
            raise TimeoutError("timed out waiting for the stream headers")

        block = self.is_alive()

        # if any leftover data available, return the first one
        if self._carryover is not None:
            (id, data) = next(
                ((k, v) for k, v in self._carryover.items() if v is not None)
            )
            self._carryover[id] = None
            if all((k for k, v in self._carryover.items() if v is None)):
                self._carryover = None
            return self.reader.streams[id]["spec"], data

        # get next chunk
        try:
            if timeout is not None:
                timeout = tend - _time()
                assert timeout > 0
            chunk = self._queue.get(block, timeout)
            if chunk is None:
                raise ThreadNotActive("reached end-of-stream")
            id, data = chunk
        except Empty:
            raise TimeoutError("timed out waiting for next chunk")
        self._queue.task_done()

        return self.reader.streams[id]["spec"], data

    def find_id(self, ref_stream):
        self.wait()
        try:
            return next(
                (k for k, v in self.reader.streams.items() if v["spec"] == ref_stream)
            )
        except:
            ValueError(f"{ref_stream} is not a valid stream specifier")

    def read(self, n=-1, ref_stream=None, timeout=None):
        """read data from all streams

        :param n: number of samples, negate to non-blocking, defaults to -1
        :type n: int, optional
        :param ref_stream: stream specifier to count the samples,
                           defaults to None (first stream)
        :type ref_stream: str, optional
        :param timeout: timeout in seconds, defaults to None (waits indefinitely)
        :type timeout: float, optional
        :raises TimeoutError: if terminated due to timeout
        :return: tuple of stream specifier and data array
        :return: dict of data array keyed by stream specifier string
        :rtype: dict(spec:str, data:numpy.ndarray)
        """

        # wait till matching line is read by the thread
        block = self.is_alive() and n != 0
        tend = timeout and (_time() + timeout)

        # if stream header not received in time, raise error
        if not self.wait(timeout):
            raise TimeoutError("timed out waiting for the stream headers")

        # get the reference stream id
        if ref_stream is None:
            ref_stream = self._ids[0]
        else:
            ref_stream = self.find_id(ref_stream)

        # identify how many samples are needed for each stream
        n_ref = max(n, -n)
        t_ref = (self._nread[ref_stream] + n_ref) / self.rates[ref_stream]
        n_need = {
            k: ceil(t_ref * self.rates[k]) - self._nread[k]
            if k != ref_stream
            else n_ref
            for k in self._ids
        }
        n_remain = deepcopy(n_need)

        # initialize output arrays
        arrays = {k: [] for k in self._ids}

        # grab any leftover data from previous read
        if self._carryover is not None:
            for k, v in self._carryover.items():
                if v is not None:
                    arrays[k] = [v]
                    n_remain[k] -= v.shape[0]
            self._carryover = None

        # loop till enough data are collected
        while any((v > 0 for k, v in n_remain.items() if n_need[k] > 0)):
            try:
                if timeout:
                    timeout = tend - _time()
                    if timeout <= 0:
                        break
                chunk = self._queue.get(block, timeout)
                if chunk is None:
                    break
                k, data = chunk
                self._queue.task_done()
                arrays[k].append(data)
                n_remain[k] -= data.shape[0]
            except Empty:
                break

        def combine(id, array, n, nr):
            # combine all the data and return requested amount
            if not len(array):
                return (id, None, None)
            all_data = _np.concatenate(array)
            return (
                (id, all_data, None)
                if nr >= 0
                else (id, all_data[:n, ...], all_data[n:, ...])
            )

        ids, data, excess = zip(
            *(
                combine(id, array, n_need[id], n_remain[id])
                for id, array in arrays.items()
            )
        )

        # any excess samples, store as a _carryover dict
        if any((sdata is not None for sdata in excess)):
            self._carryover = {id: sdata for id, sdata in zip(ids, excess)}

        # final formatting of data
        out = {}
        for id, sdata in zip(ids, data):
            info = self.reader.streams[id]
            spec = info["spec"]
            if sdata is None:
                out[spec] = _np.empty((0, *info["shape"]), info["dtype"])
            else:
                self._nread[id] += sdata.shape[0]
                out[spec] = sdata

        return out

    def readall(self, timeout=None):

        # wait till matching line is read by the thread
        if timeout is not None:
            timeout = _time() + timeout

        # if stream header not received in time, raise error
        if not self.wait(timeout):
            raise TimeoutError("timed out waiting for the stream headers")

        # initialize output arrays
        arrays = {k: [] for k in self._ids}

        # grab any leftover data from previous read
        if self._carryover is not None:
            for k, v in self._carryover.items():
                if v is not None:
                    arrays[k] = [v]
                    self._nread[k] += v.shape[0]
            self._carryover = None

        # loop till enough data are collected
        while True:
            try:
                chunk = self._queue.get(self.is_alive(), timeout and timeout - _time())
                if chunk is None:
                    break  # end of stream
                k, data = chunk
                self._queue.task_done()
                arrays[k].append(data)
                self._nread[k] += data.shape[0]
            except Empty:
                break

        # final formatting of data
        out = {}
        for id, sdata in arrays.items():
            info = self.reader.streams[id]
            spec = info["spec"]
            out[spec] = (
                _np.empty((0, *info["shape"]), info["dtype"])
                if sdata is None
                else _np.concatenate(sdata)
            )

        return out
