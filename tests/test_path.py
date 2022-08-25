import os
import pytest
from ffmpegio import path


def test_find():
    print(path.find())  # gotta have ffmpeg to run the tests

    ffmpeg_path = path.where()
    ffprobe_path = path.where(True)

    path.find(ffmpeg_path, ffprobe_path)
    with pytest.raises(Exception):
        path.find("wrong_dir")
    with pytest.raises(Exception):
        path.find("wrong_path", ffprobe_path)
    with pytest.raises(Exception):
        path.find(ffmpeg_path, "wrong_path")
    with pytest.raises(Exception):
        path.find(None, ffprobe_path)

    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    if ffmpeg_dir != "":
        path.find(ffmpeg_dir)


def test_found():
    assert path.found()  # assuming ffmpeg is found in a default place


def test_where():
    assert path.where() is not None  # assuming ffmpeg is found

def test_versions():
    assert "version" in path.versions()

def test_check_version():
    path.check_version("5.0")
    path.check_version("5.0","==")
    path.check_version("5.0","!=")
    path.check_version("5.0","<")
    path.check_version("5.0",">")
    path.check_version("5.0","<=")
    path.check_version("5.0",">=")

if __name__ == "__main__":
    test_find()
