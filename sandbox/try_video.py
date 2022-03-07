import logging
import ffmpegio
import logging

logging.basicConfig(level=logging.DEBUG)

url = "smptebars=r=45:s=1920x1080:d=180"

# fg = "[0:a][1:a]amix=weights=1|2[out]"
# fg = "[1:a]adelay=3000,apad,asplit=2[sc][mix];[0:a][sc]sidechaincompress=threshold=0.003:ratio=20[bg];[bg][mix]amix=duration=shortest[out]"

for i in range(10):
    ffmpegio.ffmpegprocess.run(
        {
            "inputs": [(url, {"f": "lavfi"})],
            "outputs": [("sandbox/output.mp4", {"r": 5})],
            # "global_options": {"filter_complex": fg},
        },
        overwrite=True,
    )
