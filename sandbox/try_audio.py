import logging
import ffmpegio
import logging
logging.basicConfig(level=logging.DEBUG)

url_long = "sandbox/long.mp3"
url_short = "sandbox/short.mp3"

url_long = "anoisesrc=d=60:c=pink:r=44100:a=0.5"
url_short = "sine=220:4:d=5"

# fg = "[0:a][1:a]amix=weights=1|2[out]"
fg = "[1:a]adelay=3000,apad,asplit=2[sc][mix];[0:a][sc]sidechaincompress=threshold=0.003:ratio=20[bg];[bg][mix]amix=duration=shortest[out]"

ffmpegio.ffmpegprocess.run(
    {
        "inputs": [(url_long, {'f':'lavfi'}), (url_short, {'f':'lavfi'})],
        "outputs": [("sandbox/output.mp3", {"map": "[out]"})],
        "global_options": {"filter_complex": fg},
    },
    overwrite=True,
)
