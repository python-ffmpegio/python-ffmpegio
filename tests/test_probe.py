import logging

logging.basicConfig(level=logging.DEBUG)
import pytest

import ffmpegio.probe as probe

# print(
#     probe.inquire(
#         "tests/assets/testvideo-5m.mpg",
#         show_format=True,
#         show_streams=("index", "codec_name"),
#         show_programs=False,
#     )
# )


def test_probe():
    probe.ffprobe("-help")


def test_all():
    url = "tests/assets/testmulti-1m.mp4"
    print(probe.full_details(url, show_streams="v"))
    print(probe.format_basic(url))
    print(probe.video_streams_basic(url))
    print(probe.audio_streams_basic(url))


def test_query():
    url = "tests/assets/testmulti-1m.mp4"
    print(probe.query(url, fields=("duration",)))
    print(
        probe.query(
            url, "v", fields=("duration", "r_frame_rate", "avg_frame_rate", "pix_fmt")
        )
    )
    print(probe.query(url, "a", fields=("duration", "sample_rate", "sample_fmt")))
    print(probe.query(url))

    with pytest.raises(ValueError):
        probe.query(url, "a", fields=("duration", "bad_filed"))

    assert (
        probe.query(url, "a", fields=("duration", "bad_filed"), return_none=True)[1]
        is None
    )

def test_frames():
    url = "tests/assets/testmulti-1m.mp4"
    info = probe.frames(
        url,
        streams="a:0",
        intervals=10
        # intervals='%+#20,30%+#15'
        # intervals=[{"end_offset": 20}, {"start": 30, "end_offset": 12}],
    )
    print(len(info))
    print(info[-1])
    pts_time = probe.frames(
        url,
        "pts_time",
        "a:0",
        intervals=10
        # intervals='%+#20,30%+#15'
        # intervals=[{"end_offset": 20}, {"start": 30, "end_offset": 12}],
    )
    print(pts_time)
    pts_time1 = probe.frames(
        url,
        "pts_time",
        "a:0",
        intervals=10,
        accurate_time=True
        # intervals='%+#20,30%+#15'
        # intervals=[{"end_offset": 20}, {"start": 30, "end_offset": 12}],
    )
    print(pts_time1)
    print([t - t1 for t, t1 in zip(pts_time, pts_time1)])

    info = probe.frames(
        url,
        streams="a:0",
        intervals=(23.4, 1),
        accurate_time=True
        # intervals='%+#20,30%+#15'
        # intervals=[{"end_offset": 20}, {"start": 30, "end_offset": 12}],
    )
    print(info)

if __name__ == "__main__":
    test_all()
    pass
