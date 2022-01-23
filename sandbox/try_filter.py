import subprocess as sp
from threading import Thread
from time import sleep
from ffmpegio import get_path
from os import path
import numpy as np

ff = path.join(get_path(), "ffmpeg")


def load_setup():
    return (
        ff + f" -hide_banner -f f64le -ar 8000 -ac 1 -i - -af lowpass -f f64le -ac 1 -",
        np.ones((16000, 1)),
    )


# def load_setup():
#     return (
#         ff
#         + f" -hide_banner -f rawvideo -s 100x100 -pix_fmt rgb24 -i - -vf 'transpose' -f rawvideo -s 100x100 -",
#         np.ones((100, 100, 3), "u1"),
#     )


def reader(stdout):
    print("reading stdout...")
    y = stdout.read(1)
    print(f"  stdout: read the first byte")
    try:
        stdout.read()
    except:
        pass


def logger(stderr):
    print("log stderr...")
    l = stderr.readline()
    print(f"  stderr: {l.decode('utf8')}")
    while True:
        try:
            l = stderr.readline()
        except:
            break


cmd, x = load_setup()  # <- 2 cases: video & audio
nbytes = x.size * x.itemsize

print(cmd)

p = sp.Popen(cmd, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)

rd = Thread(target=reader, args=(p.stdout,))
rd.start()
lg = Thread(target=logger, args=(p.stderr,))
lg.start()

try:
    print("written input data to buffer")
    p.stdin.write(x)
    print("written input data")

    sleep(1)
    print("slept 1 second, closing stdin")
finally:
    p.stdin.close()
    print("stdin closed")
    p.stdout.close()
    p.stderr.close()
    rd.join()
    lg.join()
    p.wait()
