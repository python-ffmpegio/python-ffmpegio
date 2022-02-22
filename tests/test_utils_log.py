import io
import time
from ffmpegio.utils import log
from ffmpegio.ffmpegprocess import run
from tempfile import TemporaryDirectory
from os import path
import re
from pprint import pprint


def test_log_completed():
    url = "tests/assets/testmulti-1m.mp4"
    with TemporaryDirectory() as tmpdir:
        f = run(
            {
                "inputs": [(url, {"t": 0.1})],
                "outputs": [(path.join(tmpdir, "test.mp4"), None)],
                "global_options": None,
            },
            capture_log=True,
        )
        logs = re.split(r"[\n\r]+", f.stderr)

        pprint(log.extract_output_stream(logs))
        pprint(log.extract_output_stream(logs, 0, 1))


if __name__ == "__main__":

    pass
