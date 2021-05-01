from ffmpegio import ffmpeg, probe
from os import path
from pprint import pprint


url = "tests/assets/testvideo-5m.mp4"
if not path.isfile(url):
    ffmpeg.run_sync(
        {
            "inputs": [("testsrc=r=30000/1001:d=300", {"f": "lavfi"})],
            "outputs": [(url, None)],
            "global_options": {"y": None},
        }
    )
pprint(probe.full_details(url))


url = "tests/assets/testvideo-5m.mpg"
if not path.isfile(url):
    ffmpeg.run_sync(
        {
            "inputs": [("testsrc2=r=30000/1001:d=60", {"f": "lavfi"})],
            "outputs": [
                (
                    "tests/assets/testvideo-5m.mpg",
                    {
                        "flags": "+ildct+ilme",
                        "vf": "interlace=lowpass=0:scan=tff",
                        "c:v": "mpeg2video",
                    },
                )
            ],
            "global_options": {"y": None},
        }
    )
pprint(probe.full_details(url))
