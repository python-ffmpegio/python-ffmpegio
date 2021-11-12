"""Experiment of asynchronous os.pipe()/os.read()/os.write() 

3 threads, 2 pipes, 4 i/o block sizes:

1. feeder (tx to processor at rate x)
2. processor (rx from feeder at rate x1 and tx to reader at rate y)
3. reader (rx from processor at rate y1)

only reader rx is non-blocking

"""

from ffmpegio.utils import threaded_pipe as tp
import os
import threading
import time
import math


def processor(stdin, stdout, nin, nout, nblks):
    print("[processor] starting")
    nintotal = 0
    noutottal = 0
    for i in range(nblks):
        print(f"[processor n={i}]")
        nread = 0
        while nread < nin:
            indata = os.read(stdin, nin - nread)
            nread += len(indata)
        if nread != nin:
            print(f"[processor] received {nread} expecting {nin}")
        time.sleep(100e-3)

        os.write(stdout, b"0" * nout)

        nintotal += len(indata)
        noutottal += nout
        print(
            f"[processor n={i}] rx {nintotal}/{nin*nblks}, tx {noutottal}/{nout*nblks}"
        )

    os.close(stdin)
    os.close(stdout)
    print("[processor] exiting")


nblks = 3
inblks = 1
outblks = 7
g = 4

blk = 32*g * nblks * inblks * outblks // math.gcd(nblks, inblks, outblks, g)

nin = nblks * blk
nout = g * nblks * blk
timeout = 10e-3

feed = tp.ThreadedPipe(True)
read = tp.ThreadedPipe(False)

print(nin,nout)

feed.start()
read.start()

feed.open()
read.open()

proc = threading.Thread(
    target=processor,
    args=(feed.fileno(), read.fileno(), nin // nblks, nout // nblks, nblks),
)

proc.start()

try:
    feed.queue.put(b"0" * nin)

    for i in range(outblks):
        read.queue.get(True, 1)
finally:
    proc.join()
    feed.join()
    read.join()
