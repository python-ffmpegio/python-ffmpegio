from pprint import pprint
from ffmpegio import analyze, path as ffmpeg_path
import tempfile, re, logging
from os import path
import pytest

logging.basicConfig(level=logging.DEBUG)


def test_run_multi():
    loggers = [analyze.APhaseMeter(d=0.5), analyze.BBox(), analyze.BlackDetect()]
    analyze.run("tests/assets/sample.mp4", *loggers, t=10, show_log=True)
    print(loggers[0].output)
    print(loggers[1].output)
    print(loggers[2].output)


def test_run_ref():
    logger = analyze.PSNR("1:v:0")
    analyze.run(
        "tests/assets/sample.mp4",
        logger,
        references=[("tests/assets/sample.mp4", {"t": 10})],
        t=10,
        # show_log=True,
    )
    print(logger.output)


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


@pytest.mark.skipif(
    ffmpeg_path.check_version("5.1.0", "<"), reason="requires ffmpeg 5.1.0 or higher"
)
def test_blurdetect():
    url = "movie=tests/assets/sample.mp4,pad=2*iw:2*ih:(ow-iw)/2:(oh-ih)/2"
    logger = analyze.BlurDetect()
    analyze.run(url, logger, f="lavfi", t=1, show_log=True)
    assert len(logger.output.time) and len(logger.output.time) == len(
        logger.output.blur
    )


def test_astats():
    url = "tests/assets/sample.mp4"
    logger = analyze.AStats()
    analyze.run(url, logger, t=1, show_log=True)
    pprint(logger.output)


if __name__ == "__main__":
    import logging
    from matplotlib import pyplot as plt
    import ffmpegio

    logging.basicConfig(level=logging.DEBUG)

    url = "tests/assets/testvideo-1m.mp4"
    ref = "tests/assets/testvideo-1m-lowres.mp4"

    logger = analyze.PSNR()

    out = ffmpegio.ffmpeg(
        [
            "-t",
            "1",
            "-i",
            url,
            "-t",
            "1",
            "-i",
            ref,
            "-filter_complex",
            f"[0:v][1:v]{logger.filter_spec},metadata=print:file=-:direct=true",
            "-f",
            "null",
            ffmpegio.path.devnull,
        ],
        stdout=ffmpegio.path.PIPE,
        universal_newlines=True,
    )
    pprint(out.stdout)

    # analyze.run(url, logger, t=1, show_log=True)

    # pprint(logger.output)

    # assert len(logger.output.mono_interval) == 1
    # assert len(logger.output.time) == len(logger.output.value)
