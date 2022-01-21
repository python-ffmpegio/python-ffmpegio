import io
import time
from ffmpegio.utils import log
from ffmpegio.ffmpeg import exec
from ffmpegio.ffmpegprocess import Popen
from tempfile import TemporaryDirectory
from os import path
import re
from pprint import pprint


def test_log_completed():
    url = "tests/assets/testmulti-1m.mp4"
    with TemporaryDirectory() as tmpdir:
        f = exec(
            {
                "inputs": [(url, {"t": 0.1})],
                "outputs": [(path.join(tmpdir, "test.mp4"), None)],
                "global_options": None,
            },
            capture_log=True,
        )
        logs = re.split(r"[\n\r]+", f.stderr.decode("utf-8"))

        pprint(log.extract_output_stream(logs))
        pprint(log.extract_output_stream(logs, 0, 1))


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
    ) as proc, log.Logger(proc.stderr, True) as logger:
        logger.index("Output")
        pprint(logger.output_stream(0, 0))


if __name__ == "__main__":

    pass
