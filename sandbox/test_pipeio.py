"""Experiment of asynchronous os.pipe()/os.read()/os.write() 

3 threads, 2 pipes, 4 i/o block sizes:

1. feeder (tx to processor at rate x)
2. processor (rx from feeder at rate x1 and tx to reader at rate y)
3. reader (rx from processor at rate y1)

only reader rx is non-blocking

"""

from ffmpegio.utils import pipe_nonblock
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
        time.sleep(1e-3)

        os.write(stdout, b"0" * nout)

        nintotal += len(indata)
        noutottal += nout
        print(
            f"[processor n={i}] rx {nintotal}/{nin*nblks}, tx {noutottal}/{nout*nblks}"
        )

    os.close(stdin)
    os.close(stdout)
    print("[processor] exiting")


def feeder(stdin, min, inblks):
    print("[feeder] starting")
    ntotal = 0
    for i in range(inblks):
        print(f"[feeder {i}]")
        os.write(stdin, b"0" * min)
        ntotal += min
        print(f"[feeder {i}] ntotal tx'ed = {ntotal}/{min*inblks}")
    os.close(stdin)
    print("[feeder] exiting")


def reader(stdout, mout, outblks, timeout):
    print("[reader] starting")
    ntotal = 0
    for o in range(outblks):
        print(f"[reader {o}]")

        nread = 0
        while nread < mout:
            try:
                data = pipe_nonblock.read(stdout, mout - nread)
                nread += len(data)
                # print(f"[reader {o}] rx'ed {nread}/{mout} bytes")
            except pipe_nonblock.NoData:
                # print(f"[reader {o}] no data")
                time.sleep(timeout)
            if nread > mout:
                raise RuntimeError(f"rx'ed too many: {nread}/{mout}")
        ntotal += nread
        print(f"[reader {o}] ntotal = {ntotal}/{mout*outblks}")

    os.close(stdout)
    print("[reader] exiting")


txout, txin = os.pipe()
rxout, rxin = pipe_nonblock.pipe()

nblks = 3
inblks = 5
outblks = 7
g = 8

blk = g * nblks * inblks * outblks // math.gcd(nblks, inblks, outblks, g)

nin = nblks * blk
nout = g * nblks * blk
timeout = 10e-3


proc = threading.Thread(
    target=processor, args=(txout, rxin, nin // nblks, nout // nblks, nblks)
)
proc.start()

feed = threading.Thread(target=feeder, args=(txin, nin // inblks, inblks))
feed.start()

read = threading.Thread(target=reader, args=(rxout, nout // outblks, outblks, timeout))
read.start()


proc.join()
feed.join()
read.join()
