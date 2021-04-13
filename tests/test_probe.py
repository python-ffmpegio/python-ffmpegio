import ffmpegio.probe as probe

# print(
#     probe.inquire(
#         "tests/assets/testvideo-5m.mpg",
#         show_format=True,
#         show_streams=("index", "codec_name"),
#         show_programs=False,
#     )
# )

url = "tests/assets/testvideo-5m.mpg"
print(probe.inquire(url, show_streams=('codec_type',)))
print(probe.format_basic(url))
print(probe.video_streams_basic(url))
print(probe.audio_streams_basic(url))
