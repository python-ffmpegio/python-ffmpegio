from ffmpegio.utils import parser
from ffmpegio import FilterGraph


def test_ffmpeg():
    out = parser.parse("ffmpeg -i input.avi -b:v 64k -bufsize 64k output.avi")
    assert out == {
        "global_options": {},
        "inputs": [("input.avi", {})],
        "outputs": [("output.avi", {"b:v": "64k", "bufsize": "64k"})],
    }

    s = r"ffmpeg -i input.ts -filter_complex \
    '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
    -sn -map '#0x2dc' -map a output.mkv"
    assert parser.parse(s) == {
        "global_options": {
            "filter_complex": "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay"
        },
        "inputs": [("input.ts", {})],
        "outputs": [("output.mkv", {"sn": None, "map": ["#0x2dc", "a"]})],
    }

    s = "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k /tmp/a.mp2 -map 0:a -b:a 128k /tmp/b.mp2"
    p = parser.parse(s)
    assert p == {
        "global_options": {},
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
    parser.parse_options(s) == {
        "filter_complex": "\n",
        "#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay": "\n",
        "sn": None,
        "map": "#0x2dc",
    }

    s = "-i /tmp/a.wav -map 0:a -map 1:a -map 1:v -b:a 64k"
    p = parser.parse_options(s)
    assert p == {"i": "/tmp/a.wav", "map": ["0:a", "1:a", "1:v"], "b:a": "64k"}


def test_compose():
    assert (
        parser.compose(
            {
                "global_options": None,
                "inputs": [("input.avi", {})],
                "outputs": [("output.avi", {"b:v": "64k", "bufsize": "64k"})],
            }
        )
        == ["-i", "input.avi", "-b:v", "64k", "-bufsize", "64k", "output.avi"]
    )

    assert parser.compose(
        {
            "global_options": {
                "filter_complex": FilterGraph(
                    "[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay"
                )
            },
            "inputs": [("input.ts", {})],
            "outputs": [("output.mkv", {"sn": None, "map": ["#0x2dc", "a"]})],
        },
        command="ffmpeg",
    ) == [
        "ffmpeg",
        "-filter_complex",
        "[#0x2ef]setpts=PTS+1/TB[sub];[#0x2d0][sub]overlay",
        "-i",
        "input.ts",
        "-sn",
        "-map",
        "#0x2dc",
        "-map",
        "a",
        "output.mkv",
    ]

    assert (
        parser.compose(
            dict(
                inputs=[("/tmp/a.wav", {})],
                outputs=[
                    ("/tmp/a test.mp2", {"map": "0:a", "b:a": "64k"}),
                    ("/tmp/b.mp2", {"map": "0:a", "b:a": "128k"}),
                ],
            ),
            command="ffmpeg",
            shell_command=True,
        )
        == "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k '/tmp/a test.mp2' -map 0:a -b:a 128k /tmp/b.mp2"
    )
