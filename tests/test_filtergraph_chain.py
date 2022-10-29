import logging
import operator

logging.basicConfig(level=logging.INFO)

from ffmpegio import filtergraph as fg_lib
from pprint import pprint
import pytest


def test_fchain():
    fchain = fg_lib.Chain("fps=30,format=pix_fmt=rgb24,trim=0.5:12.4")
    fchain.insert(1, "overlay")
    fchain.append("split=5")
    print(type(fchain[1]))
    print(fchain)


def test_iter_pads():
    fchain = fg_lib.Chain("fps,scale2ref,overlay,split=3,concat=3")
    ins = [
        (0, 0, ("fps",)),
        (1, 0, ("scale2ref",)),
        (2, 0, ("overlay",)),
        (4, 0, ("concat", 3)),
        (4, 1, ("concat", 3)),
    ]
    outs = [
        (4, 0, ("concat", 3)),
        (3, 0, ("split", 3)),
        (3, 1, ("split", 3)),
        (1, 0, ("scale2ref",)),
    ]
    assert [*fchain.iter_input_pads()] == ins
    assert [*fchain.iter_output_pads()] == outs

    assert [*fchain.iter_input_pads(filter=4)] == ins[3:5]
    assert [*fchain.iter_output_pads(filter=3)] == outs[1:3]

    assert [*fchain.iter_input_pads(pad=1)] == ins[4:5]
    assert [*fchain.iter_output_pads(pad=1)] == outs[2:3]


# @pytest.mark.parametrize(
#     "fg,fc,left_on,right_on,out",
#     [
#         ("fps;crop", "trim", None, None, "fps,trim;crop"),
#         ("fps[out];crop", "trim", None, None, "fps[out];crop,trim"),
#     ],
# )

# if __name__ == "__main__":
def test_resolve_index():
    with pytest.raises(fg_lib.FiltergraphPadNotFoundError):
        fg_lib.Chain("color")._resolve_index(True, None)

    fchain = fg_lib.Chain("fps,scale2ref,overlay,split=3,concat=3")

    with pytest.raises(fg_lib.FiltergraphPadNotFoundError):
        fchain._resolve_index(True, 2)

    assert fchain._resolve_index(True, None) == (0, 0)
    assert fchain._resolve_index(False, None) == (4, 0)
    assert fchain._resolve_index(True, 1) == (4, 1)
    assert fchain._resolve_index(False, 1) == (3, 1)
    assert fchain._resolve_index(True, (1, 0)) == (1, 0)
    assert fchain._resolve_index(True, (4, None)) == (4, 0)
    assert fchain._resolve_index(True, (4, 1)) == (4, 1)


@pytest.mark.parametrize(
    "op, lhs,rhs,expected",
    [
        # fmt:off
        (operator.__add__, fg_lib.Chain("scale"), "overlay", "scale[L0];[L0]overlay"),
        (operator.__add__, "scale", fg_lib.Chain("overlay"), "scale[L0];[L0]overlay"),
        (operator.__rshift__, fg_lib.Chain("split"), "hflip", "split[L0];[L0]hflip"),
        (operator.__rshift__, fg_lib.Chain("split"), (1, "overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, fg_lib.Chain("split"), (1, "[in]overlay"), "split[in];[in]overlay"),
        (operator.__rshift__, fg_lib.Chain("split"), (1, 1, "overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, fg_lib.Chain("split"), (None, '[over]', "[base][over]overlay"), "split[over];[base][over]overlay"),
        (operator.__rshift__, "hflip", fg_lib.Chain("overlay"), "hflip[L0];[L0]overlay"),
        (operator.__rshift__, ("split",1), fg_lib.Chain("overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, ("split",(0,1)), fg_lib.Chain("overlay"), "split[L0];[L0]overlay"),
        (operator.__rshift__, ("split[out]",1), fg_lib.Chain("overlay"), "split[out];[out]overlay"),
        (operator.__rshift__, ("split[out]", '[out]',None), fg_lib.Chain("overlay"), "split[out];[out]overlay"),
        # (operator.__rshift__, fg_lib.Graph("split[out1][out2]"), ('[out1]', '[over]', "[base][over]overlay"), "split[out1][out2];[base][out1]overlay"),
        # fmt:on
    ],
)
def test_ops(op, lhs, rhs, expected):
    assert str(op(lhs, rhs)) == expected
