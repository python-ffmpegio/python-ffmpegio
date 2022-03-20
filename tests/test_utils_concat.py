from ffmpegio.utils.concat import ConcatDemuxer
import pytest


def test_file_item():
    filepath = "test.mp4"
    duration = 15.4
    inpoint = 1.4
    outpoint = 5.4
    metadata = {"url": "https://ffmpeg.org", "name": ".mp4"}

    item = ConcatDemuxer.FileItem(None)
    with pytest.raises(RuntimeError):
        item.lines

    item = ConcatDemuxer.FileItem(filepath)
    assert item.lines == ["file 'test.mp4'"]

    item = ConcatDemuxer.FileItem(filepath, duration, inpoint, outpoint, metadata)
    assert item.lines == [
        "file 'test.mp4'",
        "duration 15.4",
        "inpoint 1.4",
        "outpoint 5.4",
        "file_packet_meta url https://ffmpeg.org",
        "file_packet_meta name .mp4",
    ]


def test_stream_item():
    id = "v:0"
    codec = "h264"
    metadata = {"encoder": "libx264", "crf": 20}
    extradata = b"random_extra_data"

    item = ConcatDemuxer.StreamItem()
    with pytest.raises(RuntimeError):
        item.lines

    item = ConcatDemuxer.StreamItem(id, codec, metadata, extradata)
    assert item.lines == [
        "stream",
        f"exact_stream_id {id}",
        f"stream_codec {codec}",
        f"stream_meta encoder libx264",
        f"stream_meta crf 20",
        f"stream_extradata {extradata.hex()}",
    ]

    item = ConcatDemuxer.StreamItem(extradata=extradata.decode("utf8"))
    assert item.lines == ["stream", "stream_extradata random_extra_data"]


if __name__ == "__main__":
    test_stream_item()
