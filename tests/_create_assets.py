from ffmpegio import ffmpeg, probe
from os import path
from pprint import pprint

from ffmpegio import image
from matplotlib import pyplot as plt

command_list = (
    {
        "inputs": [("testsrc=r=30000/1001:d=60", {"f": "lavfi"})],
        "outputs": [("tests/assets/testvideo-1m.mp4", None)],
        "global_options": {"y": None},
    },
    {
        "inputs": [
            (
                "aevalsrc = '0.1*sin(2*PI*(360-2.5/2)*t) | 0.1*sin(2*PI*(360+2.5/2)*t)':d=60",
                {"f": "lavfi"},
            )
        ],
        "outputs": [("tests/assets/testaudio-1m.mp3", None)],
        "global_options": {"y": None},
    },
    {
        "inputs": [
            ("testsrc=r=30000/1001:d=60", {"f": "lavfi"}),
            (
                "aevalsrc = '0.1*sin(2*PI*(360-2.5/2)*t) | 0.1*sin(2*PI*(360+2.5/2)*t)':d=60",
                {"f": "lavfi"},
            ),
            ("testsrc2=d=60", {"f": "lavfi"}),
            ("anoisesrc=d=60:c=pink:r=44100:a=0.5:d=60", {"f": "lavfi"}),
        ],
        "outputs": [("tests/assets/testmulti-1m.mp4", {"map": (0, 1, 2, 3)})],
        "global_options": {"y": None},
    },
)


for cfg in command_list:
    url = cfg["outputs"][0][0]
    if not path.isfile(url):
        ffmpeg.run_sync(cfg)
    pprint(probe.full_details(url))
