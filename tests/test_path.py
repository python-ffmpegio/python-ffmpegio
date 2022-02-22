import pytest
from ffmpegio import path


def test_find():
    print(path.find())  # gotta have ffmpeg to run the tests
    with pytest.raises(Exception):
        path.find("wrong_dir")


def test_found():
    assert path.found()  # assuming ffmpeg is found in a default place


def test_where():
    assert path.where() is not None  # assuming ffmpeg is found

if __name__=='__main__':
    test_find()