from ffmpegio import threading
from ffmpegio.ffmpeg import exec
from ffmpegio.ffmpegprocess import Popen
from tempfile import TemporaryDirectory
from os import path
import re
from pprint import pprint


def test_log_popen():
    # with exec({"inputs": [(url, None)], "outputs": [("-", None)], "global_options": None},sp_run=sp.Popen,capture_log=True) as f:
    url = "tests/assets/testmulti-1m.mp4"
    with TemporaryDirectory() as tmpdir, Popen(
        {
            "inputs": [(url, {"t": 0.1})],
            "outputs": [(path.join(tmpdir, "test.mp4"), None)],
            "global_options": None,
        },
        capture_log=True,
    ) as proc, threading.LoggerThread(proc.stderr, True) as logger:
        logger.index("Output")
        pprint(logger.output_stream(0, 0))


if __name__ == "__main__":

    pass
