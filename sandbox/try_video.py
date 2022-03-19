import logging
import ffmpegio
import logging

logging.basicConfig(level=logging.DEBUG)

url1 = "smptebars=r=30:s=1280x720:d=1"
url2 = "rgbtestsrc=r=30:s=1280x720:d=1"
url3 = f"color=c=white:s=1920x1080:r=30"
url4 = "color=c=white:s=400x400:r=1,format=yuva444p,geq='lum(X,Y)':'cb(X,Y)':'cr(X,Y)':'if(lt((X-200)^2+(Y-200)^2,200^2),0,255)'"

# one.mp4
# original size: 1280x720
# position/resized: (x20, y20, w980, h:keep-aspect-ration)

# two.mp4
# original size: 1280x720
# position/resized: (x:iw-20, y:ih-20, w200, h:keep-aspect-ration)

fg = ffmpegio.FilterGraph(
    [
        ["scale=980:-1"], # 0: 1 in, 1 out
        ["crop=600:600:20:20","scale=400:-1"], # 1: 1 in, 1 out
        ["overlay=shortest=1"], # 2: 2 in, 1 out
        ["overlay=20:20:shortest=1"], # 3: 2 in, 1 out
        ["overlay=W-420:H-420"], # 4: 2 in 1 out
    ],
    input_labels={
        "0:v": (0, 0, 0), # to scale
        "1:v": (1, 0, 0), # to crop
        "2:v": (3, 0, 0), # to 1st pad of 2nd overlay (bg) (background)
        "3:v": (2, 0, 1), # to 2nd pad of 1st overlay (fg) (mask)
    },
    output_labels={"vout": (4, 0, 0)},
    links={
        (2, 0, 0): (1, 1, 0), # 2nd scale -> 1st overlay (bg)
        (3, 0, 1): (0, 0, 0), # 1st scale -> 2nd overlay (fg)
        (4, 0, 0): (3, 0, 0), # 2nd overlay -> 3rd overlay (bg)
        (4, 0, 1): (2, 0, 0), # 1st overlay -> 3rd overlay (fg)
    },
)

print(fg)

ffmpegio.ffmpegprocess.run(
    {
        "inputs": [
            (url1, {"f": "lavfi"}),
            (url2, {"f": "lavfi"}),
            (url3, {"f": "lavfi"}),
            (url4, {"f": "lavfi"}),
        ],
        "outputs": [("sandbox/output.mp4", {"map": "[vout]"})],
        "global_options": {"filter_complex": fg},
    },
    overwrite=True,
)


# fg = "[0:a][1:a]amix=weights=1|2[out]"
# fg = "[1:a]adelay=3000,apad,asplit=2[sc][mix];[0:a][sc]sidechaincompress=threshold=0.003:ratio=20[bg];[bg][mix]amix=duration=shortest[out]"

# for i in range(10):
#     ffmpegio.ffmpegprocess.run(
#         {
#             "inputs": [(url, {"f": "lavfi"})],
#             "outputs": [("sandbox/output.mp4", {"r": 5})],
#             # "global_options": {"filter_complex": fg},
#         },
#         overwrite=True,
#     )
