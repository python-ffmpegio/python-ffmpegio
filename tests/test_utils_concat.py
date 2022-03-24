from ffmpegio.utils.concat import ConcatDemuxer
from ffmpegio.utils import escape
from ffmpegio.configure import check_url
import pytest


def test_file_item():
    filepath = "test.mp4"
    duration = 15.4
    inpoint = 1.4
    outpoint = 5.4
    metadata = {"url": "https://ffmpeg.org", "name": ".mp4", "author": "Crime d'Amour"}

    item = ConcatDemuxer.FileItem(None)
    with pytest.raises(RuntimeError):
        item.lines

    item = ConcatDemuxer.FileItem(filepath)
    assert item.lines == ["file test.mp4\n"]

    item = ConcatDemuxer.FileItem(filepath, duration, inpoint, outpoint, metadata)
    assert item.lines == [
        "file test.mp4\n",
        "duration 15.4\n",
        "inpoint 1.4\n",
        "outpoint 5.4\n",
        "file_packet_meta url https://ffmpeg.org\n",
        "file_packet_meta name .mp4\n",
        f"file_packet_meta author {escape(metadata['author'])}\n",
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
        "stream\n",
        f"exact_stream_id {id}\n",
        f"stream_codec {codec}\n",
        f"stream_meta encoder libx264\n",
        f"stream_meta crf 20\n",
        f"stream_extradata {extradata.hex()}\n",
    ]

    # invalid extradata but make sure str data comes through as is
    item = ConcatDemuxer.StreamItem(extradata=extradata.decode("utf8"))
    assert item.lines == ["stream\n", "stream_extradata random_extra_data\n"]


def test_concat_demux():
    concat = ConcatDemuxer()
    assert str(concat) == "unset"  # url not set

    concat.add_file("test1.mp4", metadata={"created_by": "ffmpegio"})
    concat.add_file("test2.mp4", 5)
    concat.add_file("test3.mp4", inpoint=0.4, outpoint=10.4)
    concat.add_stream("v:0", "h264", {"performer": "me"}, b"extradata")
    concat.add_option("r", 30)
    concat.add_chapter(1, 0, 5.42)

    f = concat.compose()
    concat.parse(f.getvalue(), False)

    concat.pipe_url = "-"
    assert concat.url == "-"

    concat.pipe_url = None
    with concat:
        print(concat.url)

    print(concat.input)
    print(concat.compose().getvalue())
    print(repr(concat))

    url,fg = concat.as_filter()
    print(url,fg)


def test_url_check():
    concat = ConcatDemuxer("file vid1.mp4\nfile vid2.mp4\n", pipe_url="-")
    url, _, input = check_url(concat, nodata=False)
    assert url == concat
    assert input == concat.input


if __name__ == "__main__":
    # test_concat_demux()
    test_concat_demux()
