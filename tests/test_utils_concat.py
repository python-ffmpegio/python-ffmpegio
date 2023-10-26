from ffmpegio.utils.concat import FFConcat
from ffmpegio.utils import escape
from ffmpegio.configure import check_url
from ffmpegio.transcode import transcode
from ffmpegio.ffmpegprocess import run
import pytest, tempfile
from os import path


def test_file_item():
    filepath = "test.mp4"
    duration = 15.4
    inpoint = 1.4
    outpoint = 5.4
    metadata = {"url": "https://ffmpeg.org", "name": ".mp4", "author": "Crime d'Amour"}

    item = FFConcat.FileItem(None)
    with pytest.raises(RuntimeError):
        item.lines

    item = FFConcat.FileItem(filepath)
    assert item.lines == ["file test.mp4\n"]

    item = FFConcat.FileItem(filepath, duration, inpoint, outpoint, metadata)
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

    item = FFConcat.StreamItem()
    with pytest.raises(RuntimeError):
        item.lines

    item = FFConcat.StreamItem(id, codec, metadata, extradata)
    assert item.lines == [
        "stream\n",
        f"exact_stream_id {id}\n",
        f"stream_codec {codec}\n",
        f"stream_meta encoder libx264\n",
        f"stream_meta crf 20\n",
        f"stream_extradata {extradata.hex()}\n",
    ]

    # invalid extradata but make sure str data comes through as is
    item = FFConcat.StreamItem(extradata=extradata.decode("utf8"))
    assert item.lines == ["stream\n", "stream_extradata random_extra_data\n"]


def test_concat_demux():
    concat = FFConcat()
    assert str(concat) == "unset"  # url not set

    concat.add_file("test1.mp4", metadata={"created_by": "ffmpegio"})
    concat.add_file("test2.mp4", 5)
    concat.add_file("test3.mp4", inpoint=0.4, outpoint=10.4, options={"r": 30})
    concat.add_stream("v:0", "h264", {"performer": "me"}, b"extradata")
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

    url, fg = concat.as_filter()
    print(url, fg)


def test_url_check():
    concat = FFConcat("file vid1.mp4\nfile vid2.mp4\n", pipe_url="-")
    url, _, input = check_url(concat, nodata=False)
    assert url == concat
    assert input == concat.input


def test_transcode():
    # files = [path.abspath("tests/assets/testaudio-1m.mp3")] * 2
    url = "tests/assets/testaudio-1m.mp3"

    with tempfile.TemporaryDirectory() as tmpdirname:

        in_url = path.join(tmpdirname, "input.wav")
        transcode(url, in_url)

        out_url = path.join(tmpdirname, "output.wav")

        # example 1
        files = [in_url] * 2
        ffconcat = FFConcat()
        ffconcat.add_files(files)
        with ffconcat:
            transcode(
                ffconcat,
                out_url,
                f_in="concat",
                # protocol_whitelist_in="pipe,file",
                safe_in=0,
                codec="copy",
                # show_log=True,
                overwrite=True,
            )

        # example 2
        files = [path.basename(in_url)] * 2
        ffconcat = FFConcat(ffconcat_url=path.join(tmpdirname, "concat.txt"))
        ffconcat.add_files(files)
        with ffconcat:
            transcode(
                ffconcat,
                out_url,
                f_in="concat",
                # protocol_whitelist_in="pipe,file",
                # safe_in=0,
                codec="copy",
                show_log=True,
                overwrite=True,
            )

        # example 3
        files = [f"file:{in_url}"] * 2
        ffconcat = FFConcat(pipe_url="-")
        ffconcat.add_files(files)
        transcode(
            ffconcat,
            out_url,
            f_in="concat",
            protocol_whitelist_in="pipe,file,fd",
            safe_in=0,
            codec="copy",
            overwrite=True,
            show_log=True,
        )

        # example 4
        files = [path.basename(in_url)] * 2
        with FFConcat(ffconcat_url=path.join(tmpdirname, "concat.txt")) as ffconcat:
            ffconcat.add_files(files)
            ffconcat.update()
            transcode(
                ffconcat,
                out_url,
                f_in="concat",
                codec="copy",
                show_log=True,
                overwrite=True,
            )

        # example 5
        ffconcat = FFConcat()
        ffconcat.add_files([url] * 2)
        inputs, fg = ffconcat.as_filter(v=0, a=1)
        run(
            {
                "inputs": inputs,
                "outputs": [(out_url, None)],
                "global_options": {"filter_complex": fg},
            },
            capture_log=None,
            overwrite=True,
        )


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    # test_concat_demux()
    # test_concat_demux()
    test_transcode()
