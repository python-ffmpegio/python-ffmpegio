import ffmpegio
from pprint import pprint

url = 'rtsp://rtsp.stream/pattern'

pprint(ffmpegio.probe.full_details(url))

# args = {
#     "inputs": [(url, None)],
#     "global_options": {
#         "filter_complex": "[0:v:0]setsar=1:1,[L]concat=n=2:v=1:a=0 [v]; [0:v:1]setsar=1:1:[L]"
#     },
#     "outputs": [("sandbox/out.mp4", {"map": "[v]"})],
# }

# ffmpegio.ffmpegprocess.run(args)
