from ffmpegio.ffmpegprocess import run

url = r"tests\assets\testmulti-1m.mp4"
url2=r'tests\assets\testaudio-1m.mp3'

# run(
#     {
#         "inputs": [(url,None)],
#         "outputs": [
#             ("sandbox/out1.mp4", {"map": ["[vout1]", "[aout1]"]}),
#             ("sandbox/out2.mp4", {"map": ["[vout2]", "[aout2]"]}),
#         ],
#         "global_options": {
#             "filter_complex": "[0:v]split[vout1][vout2];[0:a]asegment=0.5[aout1][aout2]"
#         },
#     }
# )

# run(
#     {
#         "inputs": [(url, {"an": None}), (url, {"vn": None, "ss": 5})],
#         "outputs": [("sandbox/out1.mp4", {"map": ["0:v", "[aout1]"]})],
#         "global_options": {"filter_complex": "[1:a]adelay=5000:1[aout1]"},
#     },
#     overwrite=True,
# )

run(
    {
        "inputs": [(url, None)],
        "outputs": [("sandbox/out1.mp4", {"map": ["0:v", "[aout1]"]})],
        "global_options": {"filter_complex": "anullsrc,asendcmd='5-20 [enter] astreamselect map 1\,[leave] astreamselect map 0',[0:a]astreamselect=inputs=2:map=0[aout1]"},
    },
    overwrite=True,
)
