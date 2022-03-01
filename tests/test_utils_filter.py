from ffmpegio.utils import filter as filter_utils
from pprint import pprint


def test_parse_filter():
    f = "loudnorm"
    print(filter_utils.parse_filter(f))

    f = "loudnorm=print_format=summary:linear=true"
    print(filter_utils.parse_filter(f))

    f = "scale=iw/2:-1"
    print(filter_utils.parse_filter(f))

    f = r"select='eq(pict_type,I)'"
    print(filter_utils.parse_filter(f))

    f = r"drawtext=fontfile=/usr/share/fonts/truetype/DroidSans.ttf: timecode=09\:57\:00\:00: r=25: x=(w-tw)/2: y=h-(2*lh): fontcolor=white: box=1: boxcolor=0x00000000@1"
    print(filter_utils.parse_filter(f))


def test_compose_filter():
    f = "loudnorm"
    print(filter_utils.compose_filter("loudnorm"))

    f = "loudnorm=print_format=summary:linear=true"
    print(
        filter_utils.compose_filter(
            "loudnorm", dict(print_format="summary", linear=True)
        )
    )

    f = "scale=iw/2:-1"
    print(filter_utils.compose_filter("scale", "iw/2", -1))

    f = r"select='eq(pict_type\,I)'"
    print(filter_utils.compose_filter("select", "eq(pict_type,I)"))

    f = r"drawtext=fontfile=/usr/share/fonts/truetype/DroidSans.ttf: timecode='09\:57\:00\:00': r=25: \
    x=(w-tw)/2: y=h-(2*lh): fontcolor=white: box=1: boxcolor=0x00000000@1"

    print(
        filter_utils.compose_filter(
            "drawtext",
            dict(
                fontfile="/usr/share/fonts/truetype/DroidSans.ttf",
                timecode="09:57:00:00",
                r=25,
                x="(w-tw)/2",
                y="h-(2*lh)",
                fontcolor="white",
                box=1,
                boxcolor="0x00000000@1",
            ),
        )
    )


def test_compose_graph():
    f = "yadif=0:0:0,scale=iw/2:-1"
    pprint(filter_utils.compose_graph([[("yadif", 0, 0, 0), ("scale", "iw/2", -1)]]))

    f = "[1:v]negate[a]; \
    [2:v]hflip[b]; \
    [3:v]edgedetect[c]; \
    [0:v][a]hstack=inputs=2[top]; \
    [b][c]hstack=inputs=2[bottom]; \
    [top][bottom]vstack=inputs=2[out]"

    pprint(
        filter_utils.compose_graph(
            [
                [("negate",)],  # chain #0
                [("hflip",)],  # chain #1
                [("edgedetect",)],  # chain #2
                [("hstack", {"inputs": 2})],  # chain #3
                [("hstack", {"inputs": 2})],  # chain #4
                [("vstack", {"inputs": 2})],  # chain #5
            ],
            {
                "1:v": (0, 0, 0),  # feeds to negate
                "2:v": (1, 0, 0),  # feeds to hflip
                "3:v": (2, 0, 0),  # feeds to edgedetect
                "0:v": (3, 0, 0),  # feeds to the 1st input of 1st hstack
            },
            {"out": (5, 0, 0)},  # feeds from vstack output
            {  # input: output
                (3, 0, 1): (0, 0, 0),  # 1st hstack gets its 2nd input from negate
                (4, 0, 0): (1, 0, 0),  # 2nd hstack gets its 1st input from hflip
                (4, 0, 1): (2, 0, 0),  # 2nd hstack gets its 2nd input from edgedetect
                (5, 0, 0): (3, 0, 0),  # vstack gets its 1st input from 1st hstack
                (5, 0, 1): (4, 0, 0),  # vstack gets its 2nd input from 2nd hstack
            },
        )
    )

    f = "[0:v]pad=iw*2:ih*2[a]; \
    [1:v]negate[b]; \
    [2:v]hflip[c]; \
    [3:v]edgedetect[d]; \
    [a][b]overlay=w[x]; \
    [x][c]overlay=0:h[y]; \
    [y][d]overlay=w:h[out]"

    pprint(
        filter_utils.compose_graph(
            [
                [("pad", "iw*2", "ih*2")],
                [("negate",)],
                [("hflip",)],
                [("edgedetect",)],
                [("overlay", "w")],
                [("overlay", "0", "h")],
                [("overlay", "w", "h")],
            ],
            {"0:v": (0, 0, 0), "1:v": (1, 0, 0), "2:v": (2, 0, 0), "3:v": (3, 0, 0)},
            {"out": (6, 0, 0)},
            {
                (4, 0, 0): (0, 0, 0),
                (4, 0, 1): (1, 0, 0),
                (5, 0, 0): (4, 0, 0),
                (5, 0, 1): (2, 0, 0),
                (6, 0, 0): (5, 0, 0),
                (6, 0, 1): (3, 0, 0),
            },
        )
    )

    f = "[0:v]hflip,setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]overlay"

    pprint(
        filter_utils.compose_graph(
            [
                [("hflip",), ("setpts", "PTS-STARTPTS")],
                [("setpts", "PTS-STARTPTS")],
                [("overlay",)],
            ],
            {"0:v": (0, 0, 0), "1:v": (1, 0, 0)},
            links={(2, 0, 0): (0, 1, 0), (2, 0, 1): (1, 0, 0)},
        )
    )


if __name__ == "__main__":
    from ffmpegio.utils.filter import FilterGraph
    from pprint import pprint
    from ffmpegio import caps

    fall = caps.filters()
    pprint(fall['concat'])
    pprint(
        {
            k: v["num_outputs"]
            for k, v in fall.items()
            if not isinstance(v["num_outputs"], int) or v["num_outputs"] > 1
        }
    )
    pprint(
        {
            k: v["num_inputs"]
            for k, v in fall.items()
            if not isinstance(v["num_inputs"], int) or v["num_inputs"] > 1
        }
    )
