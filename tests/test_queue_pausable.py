# Some simple queue module tests, plus some failure conditions
# to ensure the Queue locks remain stable.
import threading
import time
import pytest

import ffmpegio._utils.queue_pausable as pqueue


QUEUE_SIZE = 5


@pytest.fixture
def queue():
    return pqueue.PausableQueue(QUEUE_SIZE)


def qfull(q):
    return q.maxsize > 0 and q.qsize() == q.maxsize


# A thread to run a function that unclogs a blocked Queue.
class _TriggerThread(threading.Thread):
    def __init__(self, fn, args):
        self.fn = fn
        self.args = args
        self.startedEvent = threading.Event()
        threading.Thread.__init__(self)

    def run(self):
        # The sleep isn't necessary, but is intended to give the blocking
        # function in the main thread a chance at actually blocking before
        # we unclog it.  But if the sleep is longer than the timeout-based
        # tests wait in their blocking functions, those tests will fail.
        # So we give them much longer timeout values compared to the
        # sleep here (I aimed at 10 seconds for blocking functions --
        # they should never actually wait that long - they should make
        # progress as soon as we call self.fn()).
        time.sleep(0.1)
        self.startedEvent.set()
        self.fn(*self.args)


# Execute a function that blocks, and in a separate thread, a function that
# triggers the release.  Returns the result of the blocking function.  Caution:
# block_func must guarantee to block until trigger_func is called, and
# trigger_func must guarantee to change queue state so that block_func can make
# enough progress to return.  In particular, a block_func that just raises an
# exception regardless of whether trigger_func is called will lead to
# timing-dependent sporadic failures, and one of those went rarely seen but
# undiagnosed for years.  Now block_func must be unexceptional.  If block_func
# is supposed to raise an exception, call do_exceptional_blocking_test()
# instead.


def do_blocking_test(block_func, block_args, trigger_func, trigger_args):
    thread = _TriggerThread(trigger_func, trigger_args)
    thread.start()
    try:
        result = block_func(*block_args)
        # If block_func returned before our thread made the call, we failed!
        if not thread.startedEvent.is_set():
            raise Exception(f"blocking function {block_func} appeared not to block")
        return result
    finally:
        thread.join()  # make sure the thread terminates


# Call this instead if block_func is supposed to raise an exception.
def do_exceptional_blocking_test(
    block_func, block_args, trigger_func, trigger_args, expected_exception_class
):
    thread = _TriggerThread(trigger_func, trigger_args)
    thread.start()
    try:
        try:
            block_func(*block_args)
        except expected_exception_class:
            raise
        else:
            raise Exception(f"expected exception of kind {expected_exception_class}")
    finally:
        thread.join()  # make sure the thread terminates
        if not thread.startedEvent.is_set():
            raise Exception("trigger thread ended but event never set")


class TestBaseQueue:
    def setup(self):
        self.cum = 0
        self.cumlock = threading.Lock()

    def basic_queue_test(self, q):
        if q.qsize():
            raise RuntimeError("Call this function with an empty queue")
        assert q.empty()
        assert not q.full()
        # I guess we better check things actually queue correctly a little :)
        q.put(111)
        q.put(333)
        q.put(222)
        actual_order = [q.get(), q.get(), q.get()]
        assert actual_order == [111, 333, 222], "Didn't seem to queue the correct data!"
        for i in range(QUEUE_SIZE - 1):
            q.put(i)
            assert q.qsize(), "Queue should not be empty"
        assert not qfull(q), "Queue should not be full"
        last = 2 * QUEUE_SIZE
        full = 3 * 2 * QUEUE_SIZE
        q.put(last)
        assert qfull(q), "Queue should be full"
        assert not q.empty()
        assert q.full()
        try:
            q.put(full, block=0)
            raise Exception("Didn't appear to block with a full queue")
        except pqueue.Full:
            pass
        try:
            q.put(full, timeout=0.01)
            raise Exception("Didn't appear to time-out with a full queue")
        except pqueue.Full:
            pass
        # Test a blocking put
        do_blocking_test(q.put, (full,), q.get, ())
        do_blocking_test(q.put, (full, True, 10), q.get, ())
        # Empty it
        for i in range(QUEUE_SIZE):
            q.get()
        assert not q.qsize(), "Queue should be empty"
        try:
            q.get(block=0)
            raise Exception("Didn't appear to block with an empty queue")
        except pqueue.Empty:
            pass
        try:
            q.get(timeout=0.01)
            raise Exception("Didn't appear to time-out with an empty queue")
        except pqueue.Empty:
            pass
        # Test a blocking get
        do_blocking_test(q.get, (), q.put, ("empty",))
        do_blocking_test(q.get, (True, 10), q.put, ("empty",))

    def worker(self, q):
        while True:
            x = q.get()
            if x < 0:
                q.task_done()
                return
            with self.cumlock:
                self.cum += x
            q.task_done()

    def queue_join_test(self, q):
        self.cum = 0
        threads = []
        for i in (0, 1):
            thread = threading.Thread(target=self.worker, args=(q,))
            thread.start()
            threads.append(thread)
        for i in range(100):
            q.put(i)
        q.join()
        assert self.cum == sum(
            range(100)
        ), "q.join() did not block until all tasks were done"
        for i in (0, 1):
            q.put(-1)  # instruct the threads to close
        q.join()  # verify that you can join twice
        for thread in threads:
            thread.join()

    def test_queue_task_done(self, queue):
        # Test to make sure a queue task completed successfully.
        try:
            queue.task_done()
        except ValueError:
            pass
        else:
            raise Exception("Did not detect task count going negative")

    def test_queue_join(self, queue):
        # Test that a queue join()s successfully, and before anything else
        # (done twice for insurance).
        self.queue_join_test(queue)
        self.queue_join_test(queue)
        try:
            queue.task_done()
        except ValueError:
            pass
        else:
            raise Exception("Did not detect task count going negative")

    def test_basic(self, queue):
        # Do it a couple of times on the same queue.
        # Done twice to make sure works with same instance reused.
        self.basic_queue_test(queue)
        self.basic_queue_test(queue)

    def test_negative_timeout_raises_exception(self, queue):
        with pytest.raises(ValueError):
            queue.put(1, timeout=-1)
        with pytest.raises(ValueError):
            queue.get(1, timeout=-1)

    def test_nowait(self, queue):
        for i in range(QUEUE_SIZE):
            queue.put_nowait(1)
        with pytest.raises(pqueue.Full):
            queue.put_nowait(1)

        for i in range(QUEUE_SIZE):
            queue.get_nowait()
        with pytest.raises(pqueue.Empty):
            queue.get_nowait()

    def test_shrinking_queue(self, queue):
        # issue 10110
        for i in range(QUEUE_SIZE):
            queue.put_nowait(i)
        with pytest.raises(pqueue.Full):
            queue.put_nowait(QUEUE_SIZE)
        queue.get_nowait()
        assert queue.qsize() == QUEUE_SIZE - 1
        queue.maxsize = QUEUE_SIZE - 1  # shrink the queue
        with pytest.raises(pqueue.Full):
            queue.put_nowait(QUEUE_SIZE)

    def test_queue_pause(self, queue):
        assert not queue.paused
        queue.pause()
        assert queue.paused
        with pytest.raises(pqueue.Paused):
            queue.put(0)
        with pytest.raises(pqueue.Paused):
            queue.get()
        with pytest.raises(pqueue.Paused):
            queue.task_done()
        with pytest.raises(pqueue.Paused):
            queue.join()
        queue.resume()
        assert not queue.paused
        queue.put(0)
        queue.get()

        queue.pause()
        do_blocking_test(queue.wait, (1,), queue.resume, ())

        with pytest.raises(pqueue.Paused):
            do_exceptional_blocking_test(queue.get, (), queue.pause, (), pqueue.Paused)
        
        queue.resume()
        while queue.qsize() < QUEUE_SIZE:
            queue.put_nowait(0)
        queue.pause()
        with pytest.raises(pqueue.Paused):
            do_exceptional_blocking_test(queue.put, (0,), queue.pause, (), pqueue.Paused)


# A Queue subclass that can provoke failure at a moment's notice :)
class FailingQueueException(Exception):
    pass


class FailingQueue(pqueue.PausableQueue):
    def __init__(self, *args):
        self.fail_next_put = False
        self.fail_next_get = False
        super().__init__(*args)

    def _put(self, item):
        if self.fail_next_put:
            self.fail_next_put = False
            raise FailingQueueException("You Lose")
        return super()._put(item)

    def _get(self):
        if self.fail_next_get:
            self.fail_next_get = False
            raise FailingQueueException("You Lose")
        return super()._get()


def failing_queue_test(q):
    if q.qsize():
        raise RuntimeError("Call this function with an empty queue")
    for i in range(QUEUE_SIZE - 1):
        q.put(i)
    # Test a failing non-blocking put.
    q.fail_next_put = True
    try:
        q.put("oops", block=0)
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    q.fail_next_put = True
    try:
        q.put("oops", timeout=0.1)
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    q.put("last")
    assert qfull(q), "Queue should be full"
    # Test a failing blocking put
    q.fail_next_put = True
    try:
        do_blocking_test(q.put, ("full",), q.get, ())
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    # Check the Queue isn't damaged.
    # put failed, but get succeeded - re-add
    q.put("last")
    # Test a failing timeout put
    q.fail_next_put = True
    try:
        do_exceptional_blocking_test(
            q.put, ("full", True, 10), q.get, (), FailingQueueException
        )
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    # Check the Queue isn't damaged.
    # put failed, but get succeeded - re-add
    q.put("last")
    assert qfull(q), "Queue should be full"
    q.get()
    assert not qfull(q), "Queue should not be full"
    q.put("last")
    assert qfull(q), "Queue should be full"
    # Test a blocking put
    do_blocking_test(q.put, ("full",), q.get, ())
    # Empty it
    for i in range(QUEUE_SIZE):
        q.get()
    assert not q.qsize(), "Queue should be empty"
    q.put("first")
    q.fail_next_get = True
    try:
        q.get()
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    assert q.qsize(), "Queue should not be empty"
    q.fail_next_get = True
    try:
        q.get(timeout=0.1)
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    assert q.qsize(), "Queue should not be empty"
    q.get()
    assert not q.qsize(), "Queue should be empty"
    q.fail_next_get = True
    try:
        do_exceptional_blocking_test(
            q.get, (), q.put, ("empty",), FailingQueueException
        )
        raise Exception("The queue didn't fail when it should have")
    except FailingQueueException:
        pass
    # put succeeded, but get failed.
    assert q.qsize(), "Queue should not be empty"
    q.get()
    assert not q.qsize(), "Queue should be empty"


def test_failing_queue():

    # Test to make sure a queue is functioning correctly.
    # Done twice to the same instance.
    q = FailingQueue(QUEUE_SIZE)
    failing_queue_test(q)
    failing_queue_test(q)


if __name__ == "__main__":
    # test = TestBaseQueue()
    # test.setup()
    # test.queue_join_test(pqueue.PausableQueue())

    queue = pqueue.PausableQueue()
    queue.pause()
    print(queue.paused)
    do_blocking_test(queue.wait, (1,), queue.resume, ())
