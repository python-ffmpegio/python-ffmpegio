from pprint import pprint
from ffmpegio import analyze
import tempfile, re, logging
from os import path
import pytest

logging.basicConfig(level=logging.DEBUG)


def test_aphasemeter():
    url = "amovie=tests/assets/sample.mp4,asplit[stereo],aformat=channel_layouts=mono,aformat=channel_layouts=stereo[mono];\
           [stereo]asendcmd='15.0 astreamselect map 0;17.0 astreamselect map 1',[mono]astreamselect=map=1"
    logger = analyze.APhaseMeter(d=0.5)
    analyze.run(url, logger, f="lavfi", t=10, show_log=True)
    assert len(logger.output.mono_interval) == 1
    assert len(logger.output.time) == len(logger.output.value)


def test_bbox():
    url = "movie=tests/assets/sample.mp4,pad=2*iw:2*ih:(ow-iw)/2:(oh-ih)/2"
    logger = analyze.BBox()
    analyze.run(url, logger, f="lavfi", t=1, show_log=True)
    assert len(logger.output.time) == len(logger.output.position)


if __name__ == "__main__":
    import logging
    from matplotlib import pyplot as plt

    logging.basicConfig(level=logging.DEBUG)
