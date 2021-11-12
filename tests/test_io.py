# Some simple queue module tests, plus some failure conditions
# to ensure the Queue locks remain stable.
import os
import time
import pytest
import numpy as np
from ffmpegio import io


@pytest.fixture
def reader():
    stream = io.QueuedReader()
    try:
        yield stream
    finally:
        # del stream # gc not called when test failed
        stream._pipe.join()


def feed_reader(reader, shape, ntimes=1):
    wdata = np.random.rand(*((shape,) if isinstance(shape, int) else shape))
    for _ in range(ntimes):
        os.write(reader.fileno(), wdata)
    return wdata


def test_reader(reader):
    # should open automatically
    assert not reader.closed

    assert reader.readable

    # test timout
    with pytest.raises(io.TimeoutExpired):
        reader.read(timeout=0.01)

    n = 1024
    wdata = feed_reader(reader, n)
    nbytes = n * wdata.itemsize
    rdata = reader.read(size=nbytes)
    assert bytes(wdata) == rdata

    shape = (5, 16, 64)
    wdata = feed_reader(reader, shape)
    rdata = reader.read_as_array(size=shape[0], shape=shape[1:], dtype=float)
    assert np.array_equal(wdata, rdata)


def test_reader_readall(reader):
    # should open automatically
    assert not reader.closed

    wdata = feed_reader(reader, 128, 3)
    time.sleep(0.1)

    with pytest.raises(io.TimeoutExpired):
        reader.readall(timeout=1)

    reader.mark_eof()
    rdata = reader.readall(timeout=1)
    assert len(rdata) == len(bytes(wdata)) * 3

    assert reader.closed


@pytest.fixture
def writer():
    stream = io.QueuedWriter()
    try:
        yield stream
    finally:
        # del stream # gc not called when test failed
        stream._pipe.join()


def test_writer(writer):
    # should open automatically
    assert not writer.closed

    assert writer.writable

    n = 128
    wdata = np.random.rand(n)
    writer.write(wdata, copy=True)
    writer.write(wdata, copy=False)
    nbytes = n * wdata.itemsize
    rdata = os.read(writer.fileno(), nbytes)
    assert rdata == bytes(wdata)
    rdata = os.read(writer.fileno(), nbytes)
    assert rdata == bytes(wdata)
    writer.write(wdata)
    writer.write(wdata)
    writer.write(wdata)
    rdata = os.read(writer.fileno(), 3 * nbytes)
    assert rdata[:nbytes] == bytes(wdata)


@pytest.fixture
def logger():
    stream = io.QueuedLogger()
    try:
        yield stream
    finally:
        # del stream # gc not called when test failed
        stream._pipe.join()


def feed_logger(logger, nlines=1):
    def create_n_write(i):
        line = f"line {i}\n"
        if i > 0:
            sublines = [f"   subline {j}\n" for j in range(i - 1)]
            line += "".join(sublines)
        os.write(logger.fileno(), line.encode("utf-8"))
        return line[:-1]

    return [create_n_write(i) for i in range(nlines)]


def test_logger(logger):
    # should open automatically
    assert not logger.closed

    assert logger.readable

    # test timout
    with pytest.raises(io.TimeoutExpired):
        logger.readline(timeout=0.01)

    n = 10
    wlines = feed_logger(logger, n)

    for wline in wlines[:2]:
        rline = logger.readline()
        assert wline == rline
    wlines = wlines[2:]

    part = logger.readline(3)
    rest = logger.readline()
    assert wlines[0] == part + rest
    wlines = wlines[1:]

    rlines = logger.readlines(len(wlines[0]) + 1)
    for i, rline in enumerate(rlines):
        assert wlines[i] == rline


if __name__ == "__main__":

    pass
