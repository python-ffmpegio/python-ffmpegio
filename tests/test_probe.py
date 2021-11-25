import pytest
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


def test_all():
    url = "tests/assets/testmulti-1m.mp4"
    print(probe.full_details(url, show_streams=("codec_type",)))
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


if __name__ == "__main__":
    pass
