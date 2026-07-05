from os import path
from pprint import pprint

from ffmpegio import ffmpegprocess, probe

command_list = (
    {
        "inputs": [("testsrc=r=30000/1001:d=60", {"f": "lavfi"})],
        "outputs": [("tests/assets/testvideo-1m.mp4", None)],
        "global_options": {},
    },
    {
        "inputs": [("testsrc=r=30000/1001:d=60", {"f": "lavfi"})],
        "outputs": [("tests/assets/testvideo-1m-lowres.mp4", {"crf": 25})],
        "global_options": {},
    },
    {
        "inputs": [
            (
                "aevalsrc = '0.1*sin(2*PI*(360-2.5/2)*t) | 0.1*sin(2*PI*(360+2.5/2)*t)':d=60",
                {"f": "lavfi"},
            )
        ],
        "outputs": [("tests/assets/testaudio-1m.mp3", None)],
        "global_options": {},
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
        "global_options": {},
    },
    {
        "inputs": [("testsrc=r=1:d=5", {"f": "lavfi"})],
        "outputs": [("tests/assets/imgs/testimage-%d.png", None)],
        "global_options": {},
    },
)

overwrite = True

for cfg in command_list:
    url = cfg["outputs"][0][0]
    if overwrite or not path.isfile(url):
        ffmpegprocess.run(cfg, overwrite=overwrite)
    url = url.replace("%d", "1")
    pprint(probe.full_details(url))
