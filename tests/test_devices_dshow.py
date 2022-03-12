import logging, os
from ffmpegio.plugins.devices import dshow
import pytest


@pytest.mark.skipif(os.name != "nt", reason="only run on windows")
def test_dshow():
    dshow._rescan()
    devs = dshow._list_sources()
    for spec in devs.keys():
        dshow._resolve("source", spec)
        dshow._list_options("source", spec)
    dshow._resolve("source", "|".join(devs.keys()))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    import ffmpegio

    if ffmpegio.path.FFMPEG_VER!='5.0':
        v5 = r"C:\Users\tikuma\AppData\Local\Programs\ffmpeg-5.0\bin"
        ffmpegio.set_path(fr"{v5}\ffmpeg.exe", fr"{v5}\ffprobe.exe")
        print(ffmpegio.path.FFMPEG_VER)

    test_dshow()
    