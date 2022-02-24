import ffmpegio

vf = ffmpegio.FilterGraph(
    [
        [("color", {"c": "red", "s": "1280x30"})],
        [
            ("color", {"c": "blue", "s": "1280x30"}),
            ("scale", "max(t/5*in_w,1)", "in_h", {"eval": "frame"}),
        ],
        [("overlay", 0, 0)],
        [("overlay", 0, 720 - 30, {"shortest": 1})],
    ],
    input_labels={"0": (3, 0, 0)},
    output_labels={"out": (3, 0, 0)},
    links={(2, 0, 0): (0, 0, 0), (2, 0, 1): (1, 1, 0), (3, 0, 1): (2, 0, 0)},
)

vf = ffmpegio.FilterGraph(
    [
        [("drawbox", 0, 720 - 30, 1280, 30, "white", "fill")],
        [
            ("color", {"c": "blue", "s": "1280x30"}),
            ("scale", "max(t/5*in_w,1)", "in_h", {"eval": "frame"}),
        ],
        [("overlay", 0, 720 - 30, {"shortest": 1})],
    ],
    input_labels={"in": (0, 0, 0)},
    output_labels={"out": (2, 0, 0)},
    links={(2, 0, 0): (0, 0, 0), (2, 0, 1): (1, 1, 0)},
)

# vf = ffmpegio.FilterGraph(
#     [
#         [("color", {"c": "red", "s": "1280x30"})],
#         [("color", {"c": "blue", "s": "1280x30"})],
#         [("overlay", "(t/5-1)*main_w", 0, {"eval": "frame"})],
#         [("overlay", 0, 720 - 30, {"shortest": 1})],
#     ],
#     input_labels={"0": (3, 0, 0)},
#     output_labels={"out": (3, 0, 0)},
#     links={(2, 0, 0): (0, 0, 0), (2, 0, 1): (1, 0, 0), (3, 0, 1): (2, 0, 0)},
# )

# vf = ffmpegio.FilterGraph(
#     [
#         [("drawbox", 0, 720 - 30, 1280, 30, "white", "fill")],
#         [("color", {"c": "blue", "s": "1280x30"})],
#         [("overlay", "(t/5-1)*w", 720 - 30, {"eval": "frame", "shortest": 1})],
#     ],
#     input_labels={"in": (0, 0, 0)},
#     output_labels={"out": (2, 0, 0)},
#     links={(2, 0, 0): (0, 0, 0), (2, 0, 1): (1, 0, 0)},
# )

print(vf)

ffmpegio.transcode(
    "color=c=black:s=1280x720:d=5",
    "sandbox/test.mp4",
    f_in="lavfi",
    t_in=5,
    vf=vf,
    show_log=True,
    overwrite=True,
)
