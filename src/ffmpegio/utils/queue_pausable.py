import logging
import threading as _threading, time as _time
from queue import Empty, Full, Queue as _Queue

class Paused(RuntimeError):
    "Exception raised by attempting to access empty buffer queue while operation is paused."
    pass


class PausableQueue(_Queue):
    """Create a pausable queue object with a given maximum size.
    If maxsize is <= 0, the queue size is infinite.

    Queue operations (put/get) can be paused by PausableQueue.pause(), which immediately
    triggers Paused exceptions on all threads that are waiting for data. While the queue
    is paused, all put/get calls immediately raise the Pause exception. Normal operation
    will resume upon calling PausableQueue.resume().
    """

    def __init__(self, maxsize=0):
        super().__init__(maxsize)

        # if buffering operation is paused, get & put operation raise
        # Paused exception
        self._paused = False

        # Notify not_paused whenever queue resumed its operation;
        # a thread waiting to put is notified then.
        self.not_paused = _threading.Condition(self.mutex)

    @property
    def paused(self):
        """Return True if buffering operation is paused."""
        with self.mutex:
            return self._paused

    def pause(self):
        """Pause the buffering operation.

        All threads that are waiting for queue to be readable/writable are notified
        so they can halt their operation and raise Paused exception.
        """
        with self.mutex:
            self._paused = True
            self.not_full.notify_all()
            self.not_empty.notify_all()
            self.all_tasks_done.notify_all()

    def wait(self, timeout=None):
        """Wait for the buffering operation to resume.

        :param timeout: A timeout for the operation in seconds (or fractions
                        thereof). default to None (wait indefinitely)
        :type timeout: float, optional

        Wait until another thread to resume the queuing operation.

        Note: Unlike put/get, there is no emergency releasing mechanism. So, use
        with care if using it with timeout=None.
        """
        with self.not_paused:
            if self._paused:
                self.not_paused.wait(timeout)

    def resume(self, clear=False):
        """Resume the buffering operation.

        :param clear: True to clear the buffer, defaults to False
        :type clear: bool, optional
        """
        with self.mutex:
            self._paused = False
            if clear:
                self.queue.clear()
            self.not_paused.notify_all()

    def task_done(self):
        """Indicate that a formerly enqueued task is complete.
        Used by Queue consumer threads.  For each get() used to fetch a task,
        a subsequent call to task_done() tells the queue that the processing
        on the task is complete.
        If a join() is currently blocking, it will resume when all items
        have been processed (meaning that a task_done() call was received
        for every item that had been put() into the queue).
        Raises a ValueError if called more times than there were items
        placed in the queue.
        """
        if self.paused:
            raise Paused
        super().task_done()

    def join(self, timeout=None):
        """Blocks until all items in the Queue have been gotten and processed.
        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer thread calls task_done()
        to indicate the item was retrieved and all work on it is complete.
        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        with self.all_tasks_done:
            while self.unfinished_tasks and not self._paused:
                if not self.all_tasks_done.wait(timeout):
                    return True

        if self.paused:
            raise Paused

    def put(self, item, block=True, timeout=None):
        """Put an item into the queue.
        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until a free slot is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Full exception if no free slot was available within that _time.
        Otherwise ('block' is false), put an item on the queue if a free slot
        is immediately available, else raise the Full exception ('timeout'
        is ignored in that case).
        """
        with self.not_full:
            if self.maxsize > 0:
                if not block:
                    if self._qsize() >= self.maxsize:
                        raise Full
                elif timeout is None:
                    while self._qsize() >= self.maxsize and not self._paused:
                        self.not_full.wait()
                elif timeout < 0:
                    raise ValueError("'timeout' must be a non-negative number")
                else:
                    endtime = _time.time() + timeout
                    while self._qsize() >= self.maxsize and not self._paused:
                        remaining = endtime - _time.time()
                        if remaining <= 0.0:
                            raise Full
                        self.not_full.wait(remaining)
            if self._paused:
                raise Paused
            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()

    def get(self, block=True, timeout=None):
        """Remove and return an item from the queue.
        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Empty exception if no item was available within that time.
        Otherwise ('block' is false), return an item if one is immediately
        available, else raise the Empty exception ('timeout' is ignored
        in that case).
        """
        with self.not_empty:
            if not block:
                if not self._qsize():
                    logging.debug('[PausableQueue::get] nonblocking nodata')
                    raise Empty
            elif timeout is None:
                while not self._qsize() and not self._paused:
                    self.not_empty.wait()
            elif timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            else:
                endtime = _time.time() + timeout
                while not self._qsize() and not self._paused:
                    remaining = endtime - _time.time()
                    if remaining <= 0.0:
                        logging.debug('[PausableQueue::get] timed out')
                        raise Empty
                    self.not_empty.wait(remaining)
            if self._paused:
                raise Paused
            item = self._get()
            self.not_full.notify()
            return item
