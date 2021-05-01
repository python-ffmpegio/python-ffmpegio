import ffmpegio.probe as probe

# print(
#     probe.inquire(
#         "tests/assets/testvideo-5m.mpg",
#         show_format=True,
#         show_streams=("index", "codec_name"),
#         show_programs=False,
#     )
# )

def test_all():
    url = "tests/assets/testmulti-1m.mp4"
    print(probe.full_details(url, show_streams=('codec_type',)))
    print(probe.format_basic(url))
    print(probe.video_streams_basic(url))
    print(probe.audio_streams_basic(url))
