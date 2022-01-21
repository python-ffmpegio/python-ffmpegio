import os, threading, logging
import time

from .queue_pausable import PausableQueue, Paused, Full, Empty
from . import pipe_nonblock as nonblock
from .pipe_nonblock import NoData


class AlreadyOpen(RuntimeError):
    "Exception raised if attempting to open already open ThreadedPipe."
    pass


class NotOpen(RuntimeError):
    "Exception raised if attempting to close closed ThreadedPipe."
    pass


class ThreadedPipe(threading.Thread):
    def __init__(
        self, is_writer, queue_size=0, block_size=2 ** 20, timeout=None, pipe_op=None
    ):
        """Subclass of threading.Thread to control data flow in or out of FFmpeg

        :param is_writer: True if thread writes to stdin of FFmpeg subprocess
                          or False to read from stdout of FFmpeg
        :type is_writer: bool
        :param queue_size: Upperbound limit on the number of data blocks that
                           can be placed in the queue, defaults to 0
        :type queue_size: int, optional
        :param block_size: maximum number of bytes to read (only relevant if
                           `is_writer=False`), defaults to 2**20 (or 1 MB)
        :type block_size: int, optional
        :param timeout: pipe read timeout (only relevant if `is_writer=False`), defaults to None (1e-3)
        :type timeout: float or None, optional
        :param pipe_op: Custom enqueue/dequeue operation, defaults to None
                        to use the default operation. See the details below.
        :type pipe_op: Callable, optional
        """
        super().__init__()
        self.timeout = 1e-3 if timeout is None or timeout <= 0.0 else timeout
        self.block_size = block_size
        self._pipe = os.pipe if is_writer else nonblock.pipe
        self._is_writer = is_writer  # true if fileno() is the reading-end of the pipe
        self._mutex = threading.Lock()  # protect fds
        self._fds = None
        self._joinreq = False

        self._new_state = threading.Condition(self._mutex)
        # self._just_opened = threading.Condition(self._mutex)
        # self._just_closed = threading.Condition(self._mutex)
        self._pipe_op = pipe_op

        self.queue = PausableQueue(queue_size)
        self.queue.pause()

    def fileno(self):
        """Return the frontend file descriptor (an integer) of the stream,
           interfacing with FFmpeg.

        :return: underlying file descriptor
        :rtype: int
        """
        with self._mutex:
            return self._fds and self._fds[not self._is_writer]

    @property
    def closed(self):
        """
        True if the pipe is closed.
        """
        with self._mutex:
            return self._fds is None

    @property
    def drained(self):
        """
        True if the pipe is closed and no data remains in the queue.
        """
        return self.closed or self.queue.empty()

    def wait_till_closed(self, timeout=None):
        """wait till the pipe is closed

        :param timeout: timeout for the operation in seconds, defaults to None
        :type timeout: float, optional
        """
        # reaches the EOF (i.e., None in queue) or empty queue
        with self._new_state:
            if self._fds is None:
                return
            self._new_state.wait(timeout)

    def open(self, clear_queue=False):
        with self._new_state:
            self._open(clear_queue)
            self._new_state.notify_all()
            # self._just_opened.notify_all()

    def close(self):
        """close the pipe but keep the thread running."""
        with self._new_state:
            self._close()
            self._new_state.notify_all()
            # self._just_closed.notify_all()

    def join(self):
        """close the pipe and terminate the thread"""
        if self._joinreq:
            return
        self._joinreq = True
        try:
            self.close()
        except Exception as e:
            logging.critical(f"[ThreadedPipe::join()] failed to close: {e}")

        # make sure paused queue is not holding back
        with self.queue.not_paused:
            self.queue.not_paused.notify_all()

        super().join()

    def run(self):
        logging.debug("[ThreadedPipe thread] starting")

        que = self.queue
        pipe_op, file_op = (
            (self._deque_op, self._fwrite)
            if self._is_writer
            else (self._enque_op, self._fread)
        )

        while not self._joinreq:

            if self.closed:
                # make sure the pipe is open, wait otherwise unless thread joining has been requested
                # loop until new pipe is opened
                with self._new_state:
                    self._new_state.wait()
            else:
                # run the pipe-queue transaction
                try:
                    # auto-close pipe if returned True
                    if pipe_op(que, file_op):
                        self.close()
                except nonblock.NoData:  # nonblock.read() returned empty
                    time.sleep(self.timeout)
                except Paused:
                    logging.critical("[ThreadedPipe thread] pipe is still open but queue is paused")
                    with que.not_paused:
                        que.not_paused.wait()
                except Exception as e:
                    if not self._joinreq:
                        logging.critical(f"[ThreadedPipe thread] pipe_op exception: {e}")

        if self._is_writer:
            que.clear()

        logging.debug("[ThreadedPipe thread] exiting")

    def _fread(self):
        """Return the backend file descriptor (an integer) of the stream,
           interfacing with the thread function.

        :return: underlying file descriptor
        :rtype: int
        """

        with self._mutex:
            if self._fds is None:
                raise NotOpen
            return nonblock.read(self._fds[0], self.block_size)
            # possibly raises nonblock.NoData

    def _fwrite(self, data):
        """Return the backend file descriptor (an integer) of the stream,
           interfacing with the thread function.

        :return: underlying file descriptor
        :rtype: int
        """

        with self._mutex:
            if self._fds is None:
                raise NotOpen
            return os.write(self._fds[1], data)

    @staticmethod
    def _enque_op(que, fread):

        # try to read data from FFmpeg (may raise nonblock.NoData)
        data = fread()

        # wait indefinitely to queue the data (may be raise Paused)
        que.put(data)

    @staticmethod
    def _deque_op(que, fwrite):

        # get next block of data from the queue
        data = que.get()  # may raise Paused
        que.task_done()

        # eof => close pipe
        if data is None:
            return True

        # send data to FFmpeg
        fwrite(data)
        return False

    def _open(self, clear_queue):
        # assume self._mutex is locked
        if self._fds is not None:
            raise AlreadyOpen
        self._fds = self._pipe()
        self.queue.resume(clear_queue)

    def _close(self):
        # assume self._mutex is locked
        if self._fds is None:
            return False  # no change in the state
        if self._is_writer:
            self.queue.pause()
        else:
            self.queue.put(None)  # enqueue eof marker

        for fd in self._fds:
            try:
                os.close(fd)
            except:
                pass
        self._fds = None
        return True  # pipe state changed
