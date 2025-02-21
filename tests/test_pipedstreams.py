import logging

logging.basicConfig(level=logging.DEBUG)

from os import path
import pytest

import ffmpegio as ff
from ffmpegio import streams

mult_url = "tests/assets/testmulti-1m.mp4"
video_url = "tests/assets/testvideo-1m.mp4"
audio_url = "tests/assets/testaudio-1m.mp3"
outext = ".mp4"


def test_PipedMediaReader():
    with streams.PipedMediaReader(mult_url, t=1) as reader:
        # data = reader.read(2)
        for data in reader:
            for k, v in data.items():
                print(f"{k}: {len(v['buffer'])}")
