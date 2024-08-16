import logging

logging.basicConfig(level=logging.INFO)

from ffmpegio import filtergraph as fgb
import pytest
import operator


def test_Filter():
    f = fgb.Filter("concat")
    print(f)
    assert f[0] == "concat"
    assert f.name == "concat"
    assert f.id is None
    print(f.info)
    # fgb.Filter('concat',2)
    # fgb.Filter('concat')
    # fgb.Filter('concat')


@pytest.mark.parametrize(
    "filter_spec,option_name,expected",
    [
        (("concat", {"n": 3}), "n", 3),
        (("concat", 3), "n", 3),
        (("concat",), "n", 2),
    ],
)
def test_filter_get_option_value(filter_spec, option_name, expected):
    f = fgb.Filter(filter_spec)
    try:
        assert f.get_option_value(option_name) == expected
    except fgb.Filter.InvalidName:
        pass  # ffmpeg version issue


@pytest.mark.parametrize(
    "filter_spec,expected",
    [
        ("overlay", 2),
        (["overlay", "no1"], 2),
        (("hstack", {"inputs": 4}), 4),
        (("afir", {"nbirs": 1}), 2),
        (("concat", {"n": 3}), 3),
        (("decimate", {"ppsrc": 1}), 2),
        (("fieldmatch", {"ppsrc": 1}), 2),
        (("headphone", "FL|FR|FC|LFE|BL|BR|SL|SR"), 9),
        (("headphone", ["FL", "FR"]), 3),
        (("headphone", {"map": "FL|FR|FC|LFE|BL|BR|SL|SR", "hrir": "multich"}), 2),
        (("interleave", {"nb_inputs": 2}), 2),
        (("mergeplanes", "0x001020", "yuv444p"), 3),
        (("mergeplanes", "0x00010210", "yuv444p"), 2),
        (("premultiply", {"inplace": 1}), 1),
        (("unpremultiply", {"inplace": 0}), 2),
        (("signature", {"nb_inputs": 2}), 2),
    ],
)
def test_filter_get_num_inputs(filter_spec, expected):
    f = fgb.Filter(filter_spec)
    try:
        assert f.get_num_inputs() == expected
    except fgb.Filter.InvalidName:
        logging.warning(f"skipped {filter_spec}: not supported by FFmpeg")


@pytest.mark.parametrize(
    "filter_spec,expected",
    [
        ("split", 2),
        (["split", 3], 3),
        (("acrossover", {"split": "1500 8000", "order": "8th"}), 3),
        (("afir", {"response": 0}), 1),
        (("aiir", {"response": 1}), 2),
        (("anequalizer", {"curves": 1}), 2),
        (("asegment", {"timestamps": [60, 150]}), 3),
        (("segment", "60|150"), 3),
        (("astreamselect", {"map": "1  0  2"}), 3),
        # (("streamselect",), None),
        (("channelsplit", {"channel_layout": "5.1"}), 6),
        (("extractplanes", "y+u+v"), 3),
        (("ebur128", {"video": 1}), 2),
        (("aphasemeter", {"video": 0}), 1),
        (("concat", {"n": 3, "v": 1, "a": 2}), 3),
        # "amovie": (None, None),  # streams(+-separated)
        # "movie": (None, None),  # streams(+-separated)
        (("movie", "dvd.vob", {"s": "v:0+#0x81"}), 2),
    ],
)
def test_filter_get_num_outputs(filter_spec, expected):

    f = fgb.Filter(filter_spec)
    try:
        assert f.get_num_outputs() == expected
    except fgb.Filter.InvalidName:
        logging.warning(f"skipped {filter_spec}: not supported by FFmpeg")


@pytest.mark.parametrize(
    "expr, pad, filter, chain,  exclude_chainable, chainable_first, ret",
    [
        ("color", None, None, None, False, False, []),
        ("vstack", None, None, None, False, False, [0, 1]),
        ("vstack", 0, None, None, False, False, [0]),
        ("vstack", 1, None, None, False, False, [1]),
        ("vstack", 2, None, None, False, False, None),
        ("vstack", -1, None, None, False, False, [1]),
        ("vstack", None, 0, None, False, False, [0, 1]),
        ("vstack", None, 1, None, False, False, None),
        ("vstack", None, None, 0, False, False, [0, 1]),
        ("vstack", None, None, 1, False, False, None),
        ("vstack", None, None, None, True, False, [0]),
        ("vstack", None, None, None, False, True, [1, 0]),
        ("vstack", None, None, None, True, True, []),
    ],
)
def test_iter_input_pads(
    expr,
    pad,
    filter,
    chain,
    exclude_chainable,
    chainable_first,
    ret,
):

    fg = fgb.Filter(expr)

    it = fg.iter_input_pads(
        pad,
        filter,
        chain,
        exclude_chainable=exclude_chainable,
        chainable_first=chainable_first,
    )

    if ret is None:
        with pytest.raises(fgb.FiltergraphInvalidIndex):
            next(it)
    else:
        for r in ret:
            index, f, out_index = next(it)
            assert index == (r,) and f == fg and out_index == None


@pytest.mark.parametrize(
    "expr, pad, filter, chain,  exclude_chainable, chainable_first, ret",
    [
        ("nullsink", None, None, None, False, False, []),
        ("split", None, None, None, False, False, [0, 1]),
        ("split", 0, None, None, False, False, [0]),
        ("split", 1, None, None, False, False, [1]),
        ("split", 2, None, None, False, False, None),
        ("split", -1, None, None, False, False, [1]),
        ("split", None, 0, None, False, False, [0, 1]),
        ("split", None, 1, None, False, False, None),
        ("split", None, None, 0, False, False, [0, 1]),
        ("split", None, None, 1, False, False, None),
        ("split", None, None, None, True, False, [0]),
        ("split", None, None, None, False, True, [1, 0]),
        ("split", None, None, None, True, True, []),
    ],
)
def test_iter_output_pads(
    expr,
    pad,
    filter,
    chain,
    exclude_chainable,
    chainable_first,
    ret,
):

    fg = fgb.Filter(expr)

    it = fg.iter_output_pads(
        pad,
        filter,
        chain,
        exclude_chainable=exclude_chainable,
        chainable_first=chainable_first,
    )

    if ret is None:
        with pytest.raises(fgb.FiltergraphInvalidIndex):
            next(it)
    else:
        for r in ret:
            index, f, in_index = next(it)
            assert index == (r,) and f == fg and in_index == None


@pytest.mark.parametrize(
    "expr, skip_if_no_input, skip_if_no_output, chainable_only, ret",
    [
        ("fps", False, False, False, 1),
        ("fps", True, True, True, 1),
        ("nullsrc", False, False, False, 1),
        ("nullsrc", True, False, False, 0),
        ("nullsink", False, False, False, 1),
        ("nullsink", False, True, False, 0),
    ],
)
def test_iter_chains(expr, skip_if_no_input, skip_if_no_output, chainable_only, ret):
    f = fgb.Filter(expr)
    chains = [*f.iter_chains(skip_if_no_input, skip_if_no_output, chainable_only)]
    assert len(chains) == ret


def test_apply():
    f = fgb.Filter("fade=in:5:20:color=yellow")
    print(str(f))

    f1 = f.apply({1: "in", 2: 4, "color": "red"})

    print(str(f1))


@pytest.mark.parametrize(
    "op, lhs,rhs,expected",
    [
        # fmt:off
        (operator.__add__, fgb.Filter("scale"), "overlay", "[UNC0]scale[L0];[L0][UNC1]overlay[UNC2]"),
        (operator.__add__, "scale", fgb.Filter("overlay"), "[UNC0]scale[L0];[L0][UNC1]overlay[UNC2]"),
        (operator.__rshift__, fgb.Filter("split"), "hflip", "[UNC0]split[L0][UNC1];[L0]hflip[UNC2]"),
        (operator.__rshift__, fgb.Filter("split"), (1, "overlay"), "[UNC0]split[UNC2][L0];[L0][UNC1]overlay[UNC3]"),
        (operator.__rshift__, fgb.Filter("split"), (1, "[in]overlay"), "[UNC0]split[UNC2][L0];[L0][UNC1]overlay[UNC3]"),  # X
        (operator.__rshift__, fgb.Filter("split"), (1, 1, "overlay"), "[UNC0]split[UNC2][L0];[UNC1][L0]overlay[UNC3]"),
        (operator.__rshift__, fgb.Filter("split"), (None, "[over]", "[base][over]overlay"), "[UNC0]split[L0][UNC1];[base][L0]overlay[UNC2]"),  # X
        (operator.__rshift__, "hflip", fgb.Filter("overlay"), "[UNC0]hflip[L0];[L0][UNC1]overlay[UNC2]"),
        (operator.__rshift__, ("split", 1), fgb.Filter("overlay"), "[UNC0]split[L0][UNC2];[UNC1][L0]overlay[UNC3]"),  # X
        (operator.__rshift__, ("split", (0, 1)), fgb.Filter("overlay"), "[UNC0]split[L0][UNC2];[UNC1][L0]overlay[UNC3]"),  # X
        (operator.__rshift__, ("split[out]", 1), fgb.Filter("overlay"), "[UNC0]split[L0][UNC2];[UNC1][L0]overlay[UNC3]"),  # X
        (operator.__rshift__, ("split[out]", "[out]", None), fgb.Filter("overlay"), "[UNC0]split[L0][UNC2];[L0][UNC1]overlay[UNC3]"),
        # X
        # (operator.__rshift__, fgb.Graph("split[out1][out2]"), ('[out1]', '[over]', "[base][over]overlay"), "split[out1][out2];[base][out1]overlay"),
        # fmt:on
    ],
)
def test_ops(op, lhs, rhs, expected):
    assert op(lhs, rhs).compose() == expected


if __name__ == "__name__":
    test_apply()
