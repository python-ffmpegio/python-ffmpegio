import os, threading, logging
import time

from .queue_pausable import PausableQueue, Paused, Full, Empty
from . import pipe_nonblock as nonblock


class AlreadyOpen(RuntimeError):
    "Exception raised if attempting to open already open ThreadedPipe."
    pass


class NotOpen(RuntimeError):
    "Exception raised if attempting to close closed ThreadedPipe."
    pass


class ThreadedPipe(threading.Thread):
    def __init__(
        self, is_writer, queue_size=0, timeout=1e-3, block_size=2 ** 20, pipe_op=None
    ):
        """Subclass of threading.Thread to control data flow in or out of FFmpeg

        :param is_writer: True if thread writes to stdin of FFmpeg subprocess
                          or False to read from stdout of FFmpeg
        :type is_writer: bool
        :param queue_size: Upperbound limit on the number of data blocks that
                           can be placed in the queue, defaults to 0
        :type queue_size: int, optional
        :param timeout: timeout, defaults to 1e-3
        :type timeout: [type], optional
        :param block_size: maximum number of bytes to read (only relevant if
                           `is_writer=False`), defaults to 2**23 (or 8 MB)
        :type block_size: int, optional
        :param pipe_op: Custom enqueue/dequeue operation, defaults to None
                        to use the default operation. See the details below.
        :type pipe_op: Callable, optional
        """
        super().__init__()
        self.timeout = timeout
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
        return self.closed and self.queue.empty()

    def wait_till_drained(self, timeout=None):
        return self.queue.join(timeout)

    def open(self, clear_queue=False):
        with self._mutex:
            self._open(clear_queue)
            self._new_state.notify()
            # self._just_opened.notify_all()

    def close(self):
        with self._mutex:
            self._close()
            # self._just_closed.notify_all()

    def join(self):
        if self._joinreq:
            return
        with self._new_state:
            self._joinreq = True
            if self._is_writer:
                self.queue.pause()
            self._new_state.notify()
        super().join()
        try:
            self.close()
        except:
            pass

    def run(self):
        logging.debug("starting ThreadedPipe thread")

        que = self.queue
        file_op = self._fwrite if self._is_writer else self._fread
        pipe_op = self._pipe_op or (
            self._deque_op if self._is_writer else self._enque_op
        )
        cv = self._new_state
        mutex = self._mutex

        while True:
            # make sure the pipe is open, wait otherwise unless thread joining has been requested
            # loop until new pipe is opened
            with cv:
                if self._fds is None and not self._joinreq:
                    cv.wait()
            if self._joinreq:  # thread join request has been issued
                try:
                    if self._fds is not None:
                        pipe_op(que, file_op)
                finally:
                    break

            # run the pipe-queue transaction
            try:
                # auto-close pipe if returned True
                if pipe_op(que, file_op):
                    try:
                        self.close()
                    except NotOpen:
                        pass
            except nonblock.NoData:  # nonblock.read() returned empty
                time.sleep(self.timeout)
            except Paused:
                logging.critical("pipe is still open but queue is paused")
            except Exception as e:
                with mutex:
                    if self._fds is None or self._joinreq:
                        # if pipe is closed, who cares
                        logging.debug(
                            f"[ThreadedPipe] pipe_op post-close exception: {e}"
                        )
                    else:
                        logging.critical(f"[ThreadedPipe] pipe_op exception: {e}")

        logging.debug("exiting ThreadedPipe thread")

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
        if self._fds is not None:
            raise AlreadyOpen
        self._fds = self._pipe()
        self.queue.resume(clear_queue)

    def _close(self):
        if self._fds is None:
            return
        if self._is_writer:
            self.queue.pause()
        else:
            self.queue.put(None)
        if self._fds is not None:
            for fd in self._fds:
                try:
                    os.close(fd)
                except:
                    pass
        self._fds = None
