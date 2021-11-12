# Some simple queue module tests, plus some failure conditions
# to ensure the Queue locks remain stable.
import logging
import os
import time
import pytest
from ffmpegio._utils.threaded_pipe import ThreadedPipe, NotOpen, Empty


@pytest.fixture
def reader():
    pipe = ThreadedPipe(False)
    yield pipe
    pipe.join()


def test_reader(reader):
    logging.basicConfig(level=logging.DEBUG)
    assert reader.fileno() is None
    assert reader.closed
    with pytest.raises(NotOpen):
        reader.close()

    reader.start()
    reader.open()
    assert not reader.closed
    assert reader.fileno() == reader._fds[1]

    wdata = b"\x7f\x45\x4c\x46\x01\x01\x01\x00"
    nblk = len(wdata)
    os.write(reader.fileno(), wdata)
    nbuf = nblk
    rdata = reader.queue.get(timeout=1)
    nbuf -= len(rdata)
    assert wdata == rdata
    with pytest.raises(Empty):
        reader.queue.get(False)
    wdata = b"\x7f\x45\x4c\x46\x01\x01\x01\x00"
    os.write(reader.fileno(), wdata)
    nbuf += nblk
    wdata = b"\x7f\x45\x4c\x46\x01\x01\x01\x00"
    os.write(reader.fileno(), wdata)
    nbuf += nblk
    while nbuf>0:
        rdata = reader.queue.get(timeout=1)
        nbuf -= len(rdata)
    assert nbuf==0

    reader.close()
    assert reader.closed


@pytest.fixture
def writer():
    pipe = ThreadedPipe(True)
    yield pipe
    pipe.join()


def test_writer(writer):
    logging.basicConfig(level=logging.DEBUG)
    assert writer.fileno() is None
    assert writer.closed
    with pytest.raises(NotOpen):
        writer.close()

    writer.start()
    writer.open()
    assert not writer.closed
    assert writer.fileno() == writer._fds[0]

    wdata = b"\x7f\x45\x4c\x46\x01\x01\x01\x00"
    writer.queue.put(wdata)
    writer.queue.put(wdata)
    writer.queue.put(wdata)

    rdata = os.read(writer.fileno(), len(wdata))
    assert wdata == rdata

    writer.close()
    assert writer.closed

def test_join(reader):
    reader.start()
    reader.open()
    assert not reader.closed
    reader.close()
    reader.join()
    reader.join()

if __name__ == "__main__":
    pass
