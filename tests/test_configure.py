from pprint import pprint

import pytest

from ffmpegio import configure
from ffmpegio import filtergraph as fgb
from ffmpegio.utils import analyze_complex_filtergraphs

vid_url = "tests/assets/testvideo-1m.mp4"
img_url = "tests/assets/ffmpeg-logo.png"
aud_url = "tests/assets/testaudio-1m.mp3"
mul_url = "tests/assets/testmulti-1m.mp4"


def test_add_url():

    url = "test.mp4"
    args = configure.empty()
    args_expected = configure.empty()
    idx, entry = configure.add_url(args, "input", url, None)
    args_expected["inputs"] = [(url, {})]
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    idx, entry = configure.add_url(args, "input", url, {"f": "rawvideo"}, update=True)
    args_expected["inputs"][0] = (url, {"f": "rawvideo"})
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    idx, entry = configure.add_url(
        args, "input", url, {"f": "mp4", "codec": "h264"}, update=True
    )
    args_expected["inputs"][0] = (url, {"f": "mp4", "codec": "h264"})
    assert idx == 0 and entry == args_expected["inputs"][0] and args == args_expected

    url2 = "test2.wav"
    idx, entry = configure.add_url(args, "input", url2, {"f": "wav"})
    args_expected["inputs"].append((url2, {"f": "wav"}))
    assert idx == 1 and entry == args_expected["inputs"][1] and args == args_expected


mul_streams = [(0, "video"), (1, "audio"), (2, "video"), (3, "audio")]
mul_vid_streams = [mul_streams[0], mul_streams[2]]


@pytest.mark.parametrize(
    ("url", "opts", "defopts", "ret"),
    [
        (mul_url, None, {}, ((mul_url, {}), {"src_type": "url"})),
        (mul_url, None, {}, ((None, {}), {"src_type": "fileobj"})),
        (mul_url, None, {}, ((None, {}), {"src_type": "buffer"})),
        (
            "color=c=pink [out0]",
            None,
            {"f": "lavfi"},
            (("color=c=pink [out0]", {"f": "lavfi"}), {"src_type": "filtergraph"}),
        ),
    ],
)
def test_process_url_inputs(url, opts, defopts, ret):

    info = ret[1]
    open_file = info["src_type"] in ("fileobj", "buffer")
    try:
        if open_file:
            fileobj = open(url, "rb")
            if info["src_type"] == "buffer":
                info["buffer"] = url = fileobj.read()
            else:
                url = info["fileobj"] = fileobj
        args = configure.empty()
        out = configure.process_url_inputs(
            args, [url if opts is None else (url, opts)], defopts
        )
        assert (args["inputs"][0], out[0]) == ret

    finally:
        if open_file:
            fileobj.close()


from functools import cache


@cache
def get_output_callables(media_type):
    return configure.get_raw_output_plugin_callables(media_type)


@pytest.mark.parametrize(
    ("inputs", "input_info", "filters_complex", "ret"),
    [
        (
            [(mul_url, {})],
            [{"src_type": "url"}],
            None,
            (
                [
                    {"map": f"0:{mtype[0]}:{j}"}
                    for (i, mtype), j in zip(mul_streams, [0, 0, 1, 1])
                ],
                [
                    {
                        "user_map": f"0:{mtype[0]}:{j}",
                        "media_type": mtype,
                        "input_file_id": 0,
                        "input_stream_id": i,
                    }
                    for (i, mtype), j in zip(mul_streams, [0, 0, 1, 1])
                ],
            ),
        ),
        (
            [(vid_url, None), (aud_url, {})],
            [{"src_type": "url"}, {"src_type": "url"}],
            None,
            (
                [{"map": "0:v:0"}, {"map": "1:a:0"}],
                [
                    {
                        "user_map": "0:v:0",
                        "media_type": "video",
                        "input_file_id": 0,
                        "input_stream_id": 0,
                    },
                    {
                        "user_map": "1:a:0",
                        "media_type": "audio",
                        "input_file_id": 1,
                        "input_stream_id": 0,
                    },
                ],
            ),
        ),
        (
            [(mul_url, {})],
            [{"src_type": "url"}],
            ["split=outputs=2"],
            (
                [{"map": "[out0]"}, {"map": "[out1]"}],
                [
                    {
                        "user_map": "out0",
                        "media_type": "video",
                        "linklabel": "[out0]",
                    },
                    {
                        "user_map": "out1",
                        "media_type": "video",
                        "linklabel": "[out1]",
                    },
                ],
            ),
        ),
    ],
)
def test_auto_map(inputs, input_info, filters_complex, ret):
    args = configure.empty()
    args["inputs"].extend(inputs)
    if filters_complex is not None:
        filters_complex, fg_info = analyze_complex_filtergraphs(
            fgb.as_filtergraph(filters_complex), args["inputs"], input_info
        )
        args["global_options"] = {"filter_complex": filters_complex}
    out = configure.auto_map(args, {}, input_info, filters_complex and fg_info)
    assert out == ret


@pytest.mark.parametrize(
    ("filters_complex", "ret"),
    [(["split=n=2"], {"[out0]": "video", "[out1]": "video"})],
)
def test_analyze_fg_outputs(filters_complex, ret):
    args = configure.empty({"filter_complex": filters_complex})
    out = configure.analyze_fg_outputs(args)
    assert out == ret


# prepare input
@pytest.fixture(scope="module")
def ffmpeg_url_inputs_mul():
    args = configure.empty()
    info = configure.process_url_inputs(args, [mul_url], {})
    yield args, info


@pytest.fixture(scope="module")
def ffmpeg_url_inputs_vid_aud():
    args = configure.empty()
    info = configure.process_url_inputs(args, [vid_url, aud_url], {})
    yield args, info


@pytest.mark.parametrize(
    ("ffmpeg_url_inputs", "filters_complex", "stream_opts", "stream_names"),
    [
        ("ffmpeg_url_inputs_mul", None, [{"map": "v"}], {}),
        ("ffmpeg_url_inputs_vid_aud", None, [{"map": "0:v:0"}, {"map": "1:a:0"}], {}),
        (
            "ffmpeg_url_inputs_mul",
            ["split=2"],
            [{"map": "[out0]"}, {"map": "[out1]"}, {"map": "a:0"}],
            {0: "out0", 1: "out1"},
        ),
    ],
)
def test_resolve_raw_output_streams(
    ffmpeg_url_inputs, filters_complex, stream_opts, stream_names, request
):

    args, input_info = request.getfixturevalue(ffmpeg_url_inputs)

    if filters_complex is None:
        fg_info = None
    else:
        filters_complex, fg_info = analyze_complex_filtergraphs(
            fgb.as_filtergraph(filters_complex), args["inputs"], input_info
        )
        args["global_options"] = {"filter_complex": filters_complex}
    out = configure.resolve_raw_output_streams(stream_opts, args, input_info)
    pprint(out)
