from ffmpegio import filter_utils

f = "loudnorm"

print(filter.compose_filter("loudnorm"))

f = "loudnorm=print_format=summary:linear=true"

print(filter.compose_filter("loudnorm", print_format="summary", linear=True))

f = "scale=iw/2:-1"
print(filter.compose_filter("scale", "iw/2", -1))

f = "select='eq(pict_type\,I)'"
print(filter.compose_filter("select", "eq(pict_type,I)"))

f = "yadif=0:0:0,scale=iw/2:-1"
print(filter.compose_chain(("yadif", 0, 0, 0), ("scale", "iw/2", -1)))

f = "[1:v]negate[a]; \
 [2:v]hflip[b]; \
 [3:v]edgedetect[c]; \
 [0:v][a]hstack=inputs=2[top]; \
 [b][c]hstack=inputs=2[bottom]; \
 [top][bottom]vstack=inputs=2[out]"

print(
    filter_utils.compose_graph(
        ("negate", [(3, 1)]),
        ("hflip", [(4, 0)]),
        ("edgedetect", [(4, 1)]),
        ((("hstack", {"inputs": 2}),), [(5, 0)]),
        ((("hstack", {"inputs": 2}),), [(5, 1)]),
        ((("vstack", {"inputs": 2}),),),
        input_labels={"0:v": 3, "1:v": 0, "2:v": 1, "3:v": 2},
        output_labels={"out": 5},
    )
)

f = "[0:v]pad=iw*2:ih*2[a]; \
 [1:v]negate[b]; \
 [2:v]hflip[c]; \
 [3:v]edgedetect[d]; \
 [a][b]overlay=w[x]; \
 [x][c]overlay=0:h[y]; \
 [y][d]overlay=w:h[out]"

print(
    filter_utils.compose_graph(
        ((("pad", "iw*2", "ih*2"),), [(4, 0)]),
        ("negate", [(4, 1)]),
        ("hflip", [(5, 1)]),
        ("edgedetect", [(6, 1)]),
        ((("overlay", "w"),), [(5, 0)]),
        ((("overlay", 0, "h"),), [(6, 0)]),
        ((("overlay", "w", "h"),),),
        input_labels={"0:v": 0, "1:v": 1, "2:v": 2, "3:v": 3},
        output_labels={"out": 6},
    )
)

f = "[0:v]hflip,setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]overlay"

print(
    filter_utils.compose_graph(
        (("hflip", ("setpts", "PTS-STARTPTS")), [(2, 0)]),
        ((("setpts", "PTS-STARTPTS")), [(2, 1)]),
        ("overlay",),
        input_labels={"0:v": 0, "1:v": 1},
    )
)

f = "drawtext=fontfile=/usr/share/fonts/truetype/DroidSans.ttf: timecode='09\:57\:00\:00': r=25: \
x=(w-tw)/2: y=h-(2*lh): fontcolor=white: box=1: boxcolor=0x00000000@1"

print(
    filter_utils.compose_filter(
        "drawtext",
        fontfile="/usr/share/fonts/truetype/DroidSans.ttf",
        timecode="09:57:00:00",
        r=25,
        x="(w-tw)/2",
        y="h-(2*lh)",
        fontcolor="white",
        box=1,
        boxcolor="0x00000000@1",
    )
)
