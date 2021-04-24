import pytest
from ffmpegio import ffmpeg


def test_ffmpeg():
    out = ffmpeg.parse("ffmpeg -i input.avi -b:v 64k -bufsize 64k output.avi")
    assert out == {
        "_global_options": {},
        "inputs": [("input.avi", {})],
        "outputs": [("output.avi", {"b:v": "64k", "bufsize": "64k"})],
    }

    s = r"ffmpeg -i input.ts -filter_complex \
    '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
    -sn -map '#0x2dc' -map a output.mkv"
    assert ffmpeg.parse(s) == {
        "_global_options": {
            "filter_complex": "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay"
        },
        "inputs": [("input.ts", {})],
        "outputs": [("output.mkv", {"sn": None, "map": ["#0x2dc", "a"]})],
    }

    s = "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k /tmp/a.mp2 -map 0:a -b:a 128k /tmp/b.mp2"
    p = ffmpeg.parse(s)
    assert p == {
        "_global_options": {},
        "inputs": [("/tmp/a.wav", {})],
        "outputs": [
            ("/tmp/a.mp2", {"map": "0:a", "b:a": "64k"}),
            ("/tmp/b.mp2", {"map": "0:a", "b:a": "128k"}),
        ],
    }


def test_parse_options():
    s = r"-filter_complex \
    '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
    -sn -map '#0x2dc'"
    ffmpeg.parse_options(s) == {
        "filter_complex": "\n",
        "#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay": "\n",
        "sn": None,
        "map": "#0x2dc",
    }

    s = "-i /tmp/a.wav -map 0:a -map 1:a -map 1:v -b:a 64k"
    p = ffmpeg.parse_options(s)
    assert p == {"i": "/tmp/a.wav", "map": ["0:a", "1:a", "1:v"], "b:a": "64k"}

    def test_compose():
        assert ffmpeg.compose(
            {}, [("input.avi", {})], [("output.avi", {"b:v": "64k", "bufsize": "64k"})]
        ) == ["-i", "input.avi", "-b:v", "64k", "-bufsize", "64k", "output.avi"]

        assert ffmpeg.compose(
            {
                "filter_complex": "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay"
            },
            [("input.ts", {})],
            [("output.mkv", {"sn": None, "map": ["#0x2dc", "a"]})],
            command="ffmpeg",
        ) == [
            "ffmpeg",
            "-filter_complex",
            "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay",
            "-i",
            "input.ts",
            "-sn",
            "-map",
            "#0x2dc",
            "-map",
            "a",
            "output.mkv",
        ]

    assert ffmpeg.compose(
        inputs=[("/tmp/a.wav", {})],
        outputs=[
            ("/tmp/a test.mp2", {"map": "0:a", "b:a": "64k"}),
            ("/tmp/b.mp2", {"map": "0:a", "b:a": "128k"}),
        ],
        command="ffmpeg",
        shell_command=True,
    ) == "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k '/tmp/a test.mp2' -map 0:a -b:a 128k /tmp/b.mp2"

def test_find():
    print(ffmpeg.find()) # gotta have ffmpeg to run the tests
    with pytest.raises(Exception):
        ffmpeg.find('wrong_dir')

def test_found():
    assert ffmpeg.found() # assuming ffmpeg is found in a default place

def test_where():
    assert ffmpeg.where() is not None # assuming ffmpeg is found

def test_versions():
    assert 'version' in ffmpeg.versions()

def test_run_sync():
    ffmpeg.run_sync("-help")

def test_run():
    proc = ffmpeg.run("-help")
    proc.communicate()
    proc.wait()

def test_probe():
    ffmpeg.ffprobe("-help")
