from ffmpegio import path, FilterGraph
import os

FFPLAY_BIN = os.path.join(os.path.dirname(path.FFMPEG_BIN), "ffplay")

fg = FilterGraph(
    [
        [
            (
                "movie",
                {
                    "filename": 'video="Logitech HD Webcam C310"',
                    "format_name": "dshow",
                    "format_opts": "rtbufsize=702000k",
                },
            )
        ],
        [
            (
                "amovie",
                {
                    "filename": 'audio="Microphone (HD Webcam C310)"',
                    "format_name": "dshow",
                },
            )
        ],
    ],
    output_labels={"out0": (0, 0, 0), "out1": (1, 0, 0)},
)

cmd = f"{FFPLAY_BIN} -f lavfi -i {fg}"
# cmd = f'{FFPLAY_BIN} -f dshow -rtbufsize 702000k -i video="Logitech HD Webcam C310":audio="Microphone (HD Webcam C310)"'
print(cmd)

os.system(cmd)
