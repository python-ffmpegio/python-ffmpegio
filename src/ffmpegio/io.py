import logging, re
from io import UnsupportedOperation
from subprocess import TimeoutExpired
import numpy as np

from .utils.threaded_pipe import NotOpen, ThreadedPipe, Paused, Full, Empty, NoData
from .utils import bytes_to_ndarray as _as_array


class IOBase:
    def __init__(
        self, is_writer, queue_size, block_size=None, timeout=None, pipe_op=None
    ) -> None:
        # create new pipe with a thread handling the data transfer
        self._pipe = ThreadedPipe(is_writer, queue_size, block_size, timeout, pipe_op)
        self._pipe.start()
        self._pipe.open()
        self._eof = False
        self.must_join = True

    def open(self, clear_buffer=True):
        """open a new pipe to FFmpeg process

        :param clear_buffer: True to clear the queue, defaults to True
        :type clear_buffer: bool, optional
        """
        if not self.closed:
            return

        # open pipe (if none open or new_pipe is true)
        self._pipe.open(clear_buffer)
        self._eof = False

    def close(self, join=False):
        """Flush and close this stream.

        :param join: True to completely shutdown the stream, False to keep the background thread running, defaults to True
        :type join: bool, optional

        This method has no effect if the file is already closed. Once the file
        is closed, any operation on the file (e.g. reading or writing) will
        raise a ValueError.

        As a convenience, it is allowed to call this method more than once;
        only the first call, however, will have an effect.
        """

        if self.must_join or join:
            self._pipe.join()
        else:
            self._pipe.close()  # close pipe but keep the thread
        self._eof = True

    @property
    def closed(self):
        """: bool:  True if the stream is closed."""
        return self._pipe.closed

    def wait_till_closed(self, timeout=None):
        """Block until the queue is closed.

        :param timeout: Maximum duration to wait in seconds, defaults to None or indefinite.
        :type timeout: float, optional
        :return: True if timeout occurred
        :rtype: bool
        """
        return self._pipe.wait_till_closed(timeout)

    def __del__(self):
        """Prepare for object destruction.
        IOBase provides a default implementation of this method that calls the close() methods on read and write ends of its pipe.
        """
        self._pipe.join()  # close the pipe and kill the thread

    def fileno(self):
        """Return the underlying file descriptor (an integer) of the stream.

        :return: underlying file descriptor
        :rtype: int
        """
        return self._pipe.fileno()

    def flush(self):
        """This does nothing for read-only and non-blocking streams."""
        pass

    def isatty(self):
        """Always return False because the stream is not interactive."""
        return False

    def mark_eof(self, block=True, timeout=None):
        """mark end-of-stream so pipe auto-closes when reaches it

        :param block: True to block until queued, defaults to True
        :type block: bool, optional
        :param timeout: seconds to block till raises Full exception, defaults
                        to None (block indefinitely)
        :type timeout: float, optional
        """
        try:
            self._pipe.queue.put(None, block, timeout)
        except Paused:
            pass

    def readable(self):
        """Always returns False as the stream does not support read operations."""
        return False

    def read(self, size=-1):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support read access.")

    def readall(self):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support read access.")

    def readinto(self, b):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support read access.")

    def readline(self, size=-1):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support read access.")

    def readlines(self, hint=-1):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support read access.")

    def seekable(self):
        """Always returns False as the stream does not support random access."""

        return False

    def seek(self, *_, **__):
        """
        :raises UnsupportedOperation: do not support random access
        """
        raise UnsupportedOperation("FFmpeg pipe do not support random access.")

    def tell(self):
        """
        :raises UnsupportedOperation: do not support random access
        """
        raise UnsupportedOperation("FFmpeg pipe do not support random access.")

    def truncate(self, *_, **__):
        """
        :raises UnsupportedOperation: do not support random access
        """
        raise UnsupportedOperation("FFmpeg pipe .")

    def writable(self):
        """Always returns False as the stream does not support write operation."""
        return False

    def write(self, b):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support write access.")

    def writelines(self, *_, **__):
        """
        :raises UnsupportedOperation: wrong pipe direction
        """
        raise UnsupportedOperation("FFmpeg pipe do not support text writing.")


class QueuedWriter(IOBase):
    """A raw binary stream representing an outgoing OS pipe

    :param queue_size: maximum data queue size, defaults to 0
    :type queue_size: int, optional

    The stream is stored in a queue and write operations to the pipe is
    performed in the internal thread, writing one item at a time popped
    from the queue.

    The pipe is open when instantiated, and the client can request closure
    by writing None to the queue. The pipe will then be closed when the
    internal thread processes the None item in the queue.
    """

    def __init__(self, queue_size=0):
        super().__init__(True, queue_size)

    def close(self, join=True, timeout=None):
        """Flush and close this stream.

        :param join: True to completely shutdown the stream, False to keep the background thread running, defaults to True
        :type join: bool, optional
        :param timeout: timeout in seconds to wait for queue to drain, defaults to None
        :type timeout: float, optional

        :raises TimeoutExpired: if the queue not closed before the timeout and forced=False

        This method has no effect if the file is already closed. Once the file
        is closed, any operation on the file (e.g. reading or writing) will
        raise a ValueError.

        As a convenience, it is allowed to call this method more than once;
        only the first call, however, will have an effect.
        """

        if not join and timeout is not None and self._pipe.wait_till_closed(timeout):
            raise TimeoutExpired
        super().close(join)

    @property
    def writable(self):
        """Always returns True."""
        return True

    def write(self, b, block=True, timeout=None, copy=True):
        """Write the given bytes to the underlying raw stream

        :param b: data to be sent to FFmpeg or None to mark EOF.
        :type b: readable buffer object or None
        :param block: True to block if queue is full
        :type block: bool, optional
        :param timeout: timeout in seconds if blocked
        :type timeout: float, optional
        :param copy: True to enqueue a copy of b, default True
        :type copy: bool, optional
        :return: the number of bytes written (can be less than the length of b in bytes)
        :rtype: int

        None is returned if the raw stream is set not to block and no
        single byte could be readily written to it.

        The caller may mutate b after this method returns only if copy=True
        (default). Use copy=False with care to increase performance
        on writing a large chunk of data at once.
        """
        if self.closed:
            raise BrokenPipeError("pipe is closed")

        # if not EOF, get byte sequence (either by copy or by casting)
        if b is not None:
            if not copy:
                try:
                    b = memoryview(b).cast("b")
                except:
                    raise RuntimeError("Failed to convert b to a memoryview object")
            elif not isinstance(b, bytes):
                try:
                    b = bytes(b)  # copy
                except:
                    raise RuntimeError("Failed to convert b to a bytes object")
        try:
            self._pipe.queue.put(b, block, timeout)
        except Full:
            return None
        if b is None:
            self._eof = True
        return 0 if b is None else len(b)

    def writelines(self, *_, **__):
        """
        :raises UnsupportedOperation: non-text stream.
        """
        raise UnsupportedOperation("Only binary write supported.")


class QueuedReader(IOBase):
    """A raw binary stream representing an incoming OS pipe

    :param queue_size: maximum data queue size, defaults to 0
    :type queue_size: int, optional
    :param block_size: maximum number of bytes to read, defaults to 2**20 (or 1 MB)
    :type block_size: int, optional
    :param timeout: seconds to allow till FFmpeg process terminates, defaults to 1e-3
    :type timeout: float, optional

    The stream is stored in a queue and stored by the internal thread reading
    from the pipe. The stored data can be read by read() or readall().

    The pipe is open when instantiated, and the client can request closure
    by call mark_eof(), which enqueues None to the buffer. The pipe will
    then be closed when read() or readall() encounters None item in the queue.
    """

    def __init__(self, queue_size=0, block_size=2 ** 20, timeout=1e-3):
        super().__init__(False, queue_size, block_size, timeout)
        self._buf = None  # holds leftover bytes from previously dequeued block

    def readable(self):
        """Always returns True."""
        return True

    def readall(self, block=True, timeout=None):
        """Read and return all the bytes from the stream until EOF.

        :param block: True to block until queued, defaults to True
        :type block: bool, optional
        :param timeout: seconds to block till raises Full exception, defaults
                        to None (block indefinitely)
        :type timeout: float, optional
        :return: bytes read
        :rtype: bytearray or numpy.ndarray

        By default, `bytearray` object is returned. If `shape` or `dtype`
        input argument is specified, the function returns `numpy.ndarray`
        of the specified format. If shape is unspecified, returns a 1D array.
        If dtype is unspecified, the dtype of the returned array is int8. If
        data sent by FFmpeg does not round out the shape and dtype, excess
        bytes are truncated.

        If non-blocking or timed out before the connection is closed,
        partially retrieved data are buffered then TimeoutExpired exception
        will be raised.

        """

        b = bytearray()

        if self._buf:
            b.extend(self._buf)
            self._buf = None
        while True:
            try:
                buf = self._pipe.queue.get(False if self.closed else block, timeout)
                if buf is None:
                    self._pipe.queue.task_done()
                    self.close()
                    break  # eof
                else:
                    b.extend(buf)
                    self._pipe.queue.task_done()
            except Empty:
                # timed out before stdin is closed, save what's read and re-raise
                self._buf = b
                raise TimeoutExpired("readall", timeout)

        return b

    def readinto(self, out, block=True, timeout=None, blksize=None):
        """Read bytes into a pre-allocated buffer

        :param b: writable object to store read bytes to
        :type b: bytes-like object
        :param block: True to block until queued, defaults to True
        :type block: bool, optional
        :param timeout: seconds to block till raises Full exception, defaults
                        to None (block indefinitely)
        :type timeout: float, optional
        :param blksize: if timed out, returns bytes to be the integer-multiple
                        blksize, default: 1
        :type blksize: int, optional
        :return: the number of bytes read
        :rtype: int

        For example, b might be a bytearray. If the object is in non-blocking
        mode and no bytes are available, None is returned.
        """

        if blksize is None or blksize <= 0:
            blksize = 1

        b = memoryview(out).cast("b")

        i = i1 = 0
        sz = len(b)
        if self._buf:
            # from dequeued buffer
            i = min(len(self._buf), sz)
            b[0:i] = memoryview(self._buf).cast("b")[0:i]
            if i == sz:
                self._buf = self._buf[i:]
                return i
            self._buf = None

        timedout = False
        while True:
            # read next block
            try:
                blk = self._pipe.queue.get(False if self.closed else block, timeout)
            except Empty:
                timedout = True
                break

            self._pipe.queue.task_done()
            if blk is None:
                self.close()
                break  # eof

            # get buffered bytes
            buf = memoryview(blk).cast("b")
            n = len(buf)
            i1 = i + n

            if i1 >= sz:  # got enough
                j = sz - i
                b[i:sz] = buf[0:j]
                self._buf = buf[j:]  # keep excess for later
                i = sz
                break  # done
            else:  # need more
                b[i:i1] = buf
                i = i1

        # raise error if timed out
        if timedout:
            self._buf = bytes(b[:i])  # put the retrieved data to temp buffer
            raise TimeoutExpired("readinto", timeout)

        # raise error if no
        if i == 0:
            logging.debug(f"[io.QueuedReader] no data (closed={self.closed})")
            raise Empty()

        # trim data if too much read
        nblks = i // blksize
        n = nblks * blksize
        if n < i1:
            # odd blocks of data, truncate
            excess = b[n:]
            if self._buf and len(self._buf):
                n0 = len(excess)
                n1 = len(self._buf)
                new_buf = bytearray(n0 + n1)
                new_buf[0:n0] = excess
                new_buf[n0 : n0 + n1] = self._buf[:n1]
                self._buf = new_buf
            else:
                self._buf = excess

            return n  # only report valid size w/out removing the copied data
        else:
            return i

    def read(self, size=-1, block=True, timeout=None):
        """Read up to size bytes from the object and return them.

        :param size: number of bytes to read, defaults to -1
        :type size: int, optional
        :param block: True to block until queued, defaults to True
        :type block: bool, optional
        :param timeout: seconds to block till raises Full exception, defaults
                        to None (block indefinitely)
        :type timeout: float, optional
        :return: bytes read
        :rtype: bytearray

        As a convenience, if size is unspecified or -1, all bytes until EOF are
        returned. Otherwise, only one system call is ever made. Fewer than size
        bytes may be returned if the operating system call returns fewer than
        size bytes.

        If 0 bytes are returned, and size was not 0, this indicates end of file.
        If the object is in non-blocking mode and no bytes are available, None
        is returned.

        The default implementation defers to readall() and readinto().
        """

        try:
            if size > 0:
                b = bytearray(size)
                n = self.readinto(b, block, timeout, 1)
                return b[:n] if n < size else b
            else:
                return self.readall(block, timeout)
        except TimeoutExpired:
            raise TimeoutExpired("read", timeout)

    def read_as_array(
        self,
        size=-1,
        block=True,
        timeout=None,
        shape=None,
        dtype=None,
        out=None,
        no_partial=False,
        shrink_if_partial=True,
    ):
        """Read up to size bytes from the object and return them.

        :param size: number of array blocks to read, defaults to -1
        :type size: int, optional
        :param block: True to block until queued, defaults to True
        :type block: bool, optional
        :param timeout: seconds to block till raises Full exception, defaults
                        to None (block indefinitely)
        :type timeout: float, optional
        :param shape: sizes of higher dimensions of the output array, default:
                      None (1d array). The first dimension is set by size parameter.
        :type shape: int, optional
        :param dtype: numpy.ndarray data type
        :type dtype: data-type, optional
        :param out: existing array to write data to
        :type out: numpy.ndarray, optional
        :param no_partial: True to require fully populated array. Throws
                           exception if failed. Default: False
        :type no_partial: bool
        :param shrink_if_partial: True to shrink numpy.ndarray if array is not
                                  filled, default: True
        :type shrink_if_partial: bool
        :return: bytes read
        :rtype: bytes

        As a convenience, if size is unspecified or -1, all bytes until EOF are
        returned. Otherwise, only one system call is ever made. Fewer than size
        bytes may be returned if the operating system call returns fewer than
        size bytes.

        If 0 bytes are returned, and size was not 0, this indicates end of file.
        If the object is in non-blocking mode and no bytes are available, None
        is returned.
        """

        try:
            if size is None or size <= 0:
                # read all, truncate excess
                b = self.readall(block, timeout)
                return (
                    np.empty((0, *shape)) if b is None else _as_array(b, shape, dtype)
                )
            else:
                if out is not None:
                    # override the following arguments
                    size = out.shape[0]
                    shape = out.shape[1:]
                    shrink_if_partial = False

                shape = (size, *(np.atleast_1d(shape) if bool(shape) else ()))
                if not out:
                    out = np.empty(shape, dtype or "b")
                shape = out.shape

                # determine the data block size
                blksize = out.itemsize  # 1 element
                if no_partial:
                    blksize *= out.size  # full array
                elif out.ndim > 1:
                    # allow partial first dimension
                    blksize *= np.prod(shape[1:])

                n = self.readinto(out.data, block, timeout, blksize)
                # raises TimeoutExpired if zero blk retrieved

                n //= blksize  # convert to # of elements

                return out[:n, ...] if shrink_if_partial and n < shape[0] else out
        except TimeoutExpired:
            raise TimeoutExpired("read_as_array", timeout)

    def readline(self, size=-1):
        """
        :raises UnsupportedOperation: does not support text read operations
        """
        raise UnsupportedOperation("QueuedReader do not support readline().")

    def readlines(self, hint=-1):
        """
        :raises UnsupportedOperation: does not support text read operations
        """
        raise UnsupportedOperation("QueuedReader do not support readlines().")


_re_newline = re.compile(r"\r\n?")
_re_block = re.compile(r"\n(?! )")


class QueuedLogger(IOBase):
    """A text stream representing an incoming OS pipe

    :param queue_size: maximum data queue size, defaults to 0
    :type queue_size: int, optional
    :param timeout: seconds to allow till FFmpeg process terminates, defaults to 10e-3
    :type timeout: float, optional

    The stream is stored in a queue and stored by the internal thread reading
    from the pipe. The stored data can be read by readline() or readlines().

    The pipe is open when instantiated, and the client can request closure
    by call mark_eof(), which enqueues None to the buffer. The pipe will
    then be closed when readline() or readlines() encounters None item in the queue.
    """

    def __init__(self, queue_size=0, timeout=10e-3):
        super().__init__(False, queue_size, 1024, timeout, QueuedLogger._pipe_op)
        # expose write file descriptor (so FFmpeg can write to it)
        self._buf = None  # store excess character for partial line reads

    @staticmethod
    def _pipe_op(que, fread):
        print("stderr read")

        # try to read data from FFmpeg
        data = fread()

        print("data", data)

        if data[-1] not in (10, 13):
            data += fread()

        # assume data always end with a newline
        lines = _split_logs(data)
        for line in lines:
            if line:
                que.put(line)

    def readable(self):
        """Always returns True."""
        return True

    def readline(self, size=-1, block=True, timeout=None):
        """Read and return one line from the stream.

        :param size: specifies at most size bytes to be read, defaults to -1
        :type size: int, optional
        :param block: True to block if queue is full
        :type block: bool, optional
        :param timeout: timeout in seconds if blocked
        :type timeout: float, optional
        """
        if self._buf:
            if size > 0:
                line = self._buf[:size]
                self._buf = self._buf[size:]
            else:
                line = self._buf
                self._buf = None
        else:
            # try to retrieve nonblocking first
            try:
                line = self._pipe.queue.get(False)
            except Empty:
                if self.closed:
                    raise Empty("pipe is closed and no more data in the queue")

                # try once again with user-specified blocking configuration
                try:
                    line = self._pipe.queue.get(block, timeout)
                except Empty:
                    # timed out before stdin is closed, save what's read and re-raise
                    raise TimeoutExpired("readline", timeout) if block else Empty

            if line is not None and size > 0 and size < len(line):
                self._buf = line[size:]
                line = line[:size]
            self._pipe.queue.task_done()
        return line

    def readlines(self, hint=-1, block=True, timeout=None):
        """Read and return a list of lines from the stream.

        :param hint: the number of lines to be read, defaults to -1
        :type hint: int, optional
        :param block: True to block if queue is full
        :type block: bool, optional
        :param timeout: timeout in seconds if blocked
        :type timeout: float, optional
        :return: list of lines
        :rtype: list

        No more lines will be read if the total size (in bytes/characters) of all lines so far exceeds hint.
        hint values of 0 or less, as well as None, are treated as no hint.

        Note that it’s already possible to iterate on file objects using for line in file: ... without calling file.readlines().

        Unlike standard Python io classes, the trailing new line character(s)
        is removed
        """

        if self._buf:
            lines = [self._buf]
            nbytes = len(self._buf)
            self._buf = None

        # try to retrieve first line nonblocking
        if self.closed:
            block = False

        lines = []
        nbytes = 0

        while hint < 0 or nbytes < hint:
            try:
                line = self._pipe.queue.get(block, timeout)
                if line is None:
                    break
                nbytes += len(line)
                lines.append(line)
                self._pipe.queue.task_done()
            except Empty:
                break

        return lines

    def read(self, size=-1):
        """
        :raises UnsupportedOperation: only support reading line-by-line
        """
        raise UnsupportedOperation("QueuedLogger do not read().")

    def readall(self):
        """
        :raises UnsupportedOperation: only support reading line-by-line
        """
        raise UnsupportedOperation("QueuedLogger do not support readall().")

    def readinto(self, b):
        """
        :raises UnsupportedOperation: only support reading line-by-line
        """
        raise UnsupportedOperation("QueuedLogger do not support readinto().")
