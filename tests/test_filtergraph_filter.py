import logging

logging.basicConfig(level=logging.INFO)

from ffmpegio import filtergraph as fg_lib
import pytest
import operator


def test_Filter():
    f = fg_lib.Filter("concat")
    print(f)
    assert f[0] == "concat"
    assert f.name == "concat"
    assert f.id is None
    print(f.info)
    # fg_lib.Filter('concat',2)
    # fg_lib.Filter('concat')
    # fg_lib.Filter('concat')


@pytest.mark.parametrize(
    "filter_spec,option_name,expected",
    [
        (("concat", {"n": 3}), "n", 3),
        (("concat", 3), "n", 3),
        (("concat",), "n", 2),
    ],
)
def test_filter_get_option_value(filter_spec, option_name, expected):
    f = fg_lib.Filter(filter_spec)
    try:
        assert f.get_option_value(option_name) == expected
    except fg_lib.Filter.InvalidName:
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
    f = fg_lib.Filter(filter_spec)
    try:
        assert f.get_num_inputs() == expected
    except fg_lib.Filter.InvalidName:
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

    f = fg_lib.Filter(filter_spec)
    try:
        assert f.get_num_outputs() == expected
    except fg_lib.Filter.InvalidName:
        logging.warning(f"skipped {filter_spec}: not supported by FFmpeg")


def test_apply():
    f = fg_lib.Filter("fade=in:5:20:color=yellow")
    print(str(f))

    f1 = f.apply({1: "in", 2: 4, "color": "red"})

    print(str(f1))


@pytest.mark.parametrize(
    "op, lhs,rhs,expected",
    [
        (operator.__add__, fg_lib.Filter("scale"), "overlay", "scale[L0];[L0]overlay"),
        (operator.__add__, "scale", fg_lib.Filter("overlay"), "scale[L0];[L0]overlay"),
        (operator.__rshift__, fg_lib.Filter("split"), "hflip", "split[L0];[L0]hflip"),
        (operator.__rshift__, fg_lib.Filter("split"), (1, "overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, fg_lib.Filter("split"), (1, "[in]overlay"), "split[in];[in]overlay"),
        (operator.__rshift__, fg_lib.Filter("split"), (1, 1, "overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, fg_lib.Filter("split"), (None, '[over]', "[base][over]overlay"), "split[over];[base][over]overlay"),
        (operator.__rshift__, "hflip", fg_lib.Filter("overlay"), "hflip[L0];[L0]overlay"),
        (operator.__rshift__, ("split",1), fg_lib.Filter("overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, ("split",(0,1)), fg_lib.Filter("overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, ("split[out]",1), fg_lib.Filter("overlay"), "split[out];[out]overlay"),
        (operator.__rshift__, ("split[out]", '[out]',None), fg_lib.Filter("overlay"), "split[out];[out]overlay"),
        # (operator.__rshift__, fg_lib.Graph("split[out1][out2]"), ('[out1]', '[over]', "[base][over]overlay"), "split[out1][out2];[base][out1]overlay"),
    ],
)
def test_ops(op, lhs, rhs, expected):
    assert str(op(lhs, rhs)) == expected


if __name__ == "__name__":
    test_apply()
