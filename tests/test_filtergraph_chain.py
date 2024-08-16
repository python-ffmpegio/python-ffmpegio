import logging
import operator

logging.basicConfig(level=logging.INFO)

from ffmpegio import filtergraph as fgb
from pprint import pprint
import pytest


def test_fchain():
    fchain = fgb.Chain("fps=30,format=pix_fmt=rgb24,trim=0.5:12.4")
    fchain.insert(1, "overlay")
    fchain.append("split=5")
    print(type(fchain[1]))
    print(fchain)


@pytest.mark.parametrize(
    "expr, pad, filter, chain, exclude_chainable, chainable_first, include_connected, ret",
    [
        # fmt: off
        ("color,nullsink", None, None, None, False, False, False, []),
        ("vstack,hstack", None, None, None, False, False, False, [(0, 0),(0, 1),(1, 0)]),
        ("vstack,hstack", None, None, 0, False, False, False, [(0, 0),(0, 1),(1, 0)]),
        ("vstack,hstack", None, None, 1, False, False, False, None),
        ("vstack,hstack", None, 0, None, False, False, False, [(0, 0),(0, 1)]),
        ("vstack,hstack", None, 1, None, False, False, False, [(1, 0)]),
        ("vstack,hstack", None, 2, None, False, False, False, None),
        ("vstack,hstack", None, None, None, True, False, False, [(0, 0),(1, 0)]),
        ("vstack,hstack", None, None, None, False, True, False, [(0, 1),(0, 0),(1, 0)]),
        ("vstack,hstack", None, None, None, False, False, True, [(0, 0),(0, 1),(1, 0),(1,1)]),
        # fmt: on
    ],
)
def test_iter_input_pads(
    expr,
    pad,
    filter,
    chain,
    exclude_chainable,
    chainable_first,
    include_connected,
    ret,
):

    fg = fgb.Chain(expr)

    it = fg.iter_input_pads(
        pad,
        filter,
        chain,
        exclude_chainable=exclude_chainable,
        chainable_first=chainable_first,
        include_connected=include_connected,
    )

    if ret is None:
        with pytest.raises(fgb.FiltergraphInvalidIndex):
            next(it)
    else:
        for r in ret:
            index, f, out_index = next(it)
            assert index == r and f == fg[r[0]]
            if out_index is not None:
                assert out_index[0] == index[0] - 1


@pytest.mark.parametrize(
    "expr, pad, filter, chain, exclude_chainable, chainable_first, include_connected, ret",
    [
        # fmt: off
        ("split,split", None, None, None, False, False, False, [(0, 0),(1, 0),(1, 1)]),
        # fmt: on
    ],
)
def test_iter_output_pads(
    expr,
    pad,
    filter,
    chain,
    exclude_chainable,
    chainable_first,
    include_connected,
    ret,
):

    fg = fgb.Chain(expr)

    it = fg.iter_output_pads(
        pad,
        filter,
        chain,
        exclude_chainable=exclude_chainable,
        chainable_first=chainable_first,
        include_connected=include_connected,
    )

    if ret is None:
        with pytest.raises(fgb.FiltergraphInvalidIndex):
            next(it)
    else:
        for r in ret:
            index, f, out_index = next(it)
            assert index == r and f == fg[r[0]]
            if out_index is not None:
                assert out_index[0] == index[0] - 1

@pytest.mark.parametrize(
    "expr, skip_if_no_input, skip_if_no_output, chainable_only, ret",
    [
        ("fps,scale", False, False, False, 1),
        ("fps,scale", True, True, True, 1),
        ("nullsrc,fps", False, False, False, 1),
        ("nullsrc,fps", True, False, False, 0),
        ("fps,nullsink", False, False, False, 1),
        ("fps,nullsink", False, True, False, 0),
    ],
)
def test_iter_chains(expr, skip_if_no_input, skip_if_no_output, chainable_only, ret):
    f = fgb.Chain(expr)
    chains = [*f.iter_chains(skip_if_no_input, skip_if_no_output, chainable_only)]
    assert len(chains) == ret


@pytest.mark.parametrize(
    "op, lhs,rhs,expected",
    [
        # fmt:off
        (operator.__add__, fgb.Chain("scale"), "overlay", "[UNC0]scale[L0];[L0][UNC1]overlay[UNC2]"),
        (operator.__add__, "scale", fgb.Chain("overlay"), "[UNC0]scale[L0];[L0][UNC1]overlay[UNC2]"),
        (operator.__rshift__, fgb.Chain("split"), "hflip", "[UNC0]split[L0][UNC1];[L0]hflip[UNC2]"),
        (operator.__rshift__, fgb.Chain("split"), (1, "overlay"), "[UNC0]split[UNC2][L0];[L0][UNC1]overlay[UNC3]"),
        (operator.__rshift__, fgb.Chain("split"), (1, "[in]overlay"), "[UNC0]split[UNC2][L0];[L0][UNC1]overlay[UNC3]"),
        (operator.__rshift__, fgb.Chain("split"), (1, 1, "overlay"), "[UNC0]split[UNC2][L0];[UNC1][L0]overlay[UNC3]"),
        (operator.__rshift__, fgb.Chain("split"), (None, '[over]', "[base][over]overlay"), "[UNC0]split[L0][UNC1];[base][L0]overlay[UNC2]"),
        (operator.__rshift__, "hflip", fgb.Chain("overlay"), "[UNC0]hflip[L0];[L0][UNC1]overlay[UNC2]"),
        (operator.__rshift__, ("split",1), fgb.Chain("overlay"), "[UNC0]split[L0][UNC2];[UNC1][L0]overlay[UNC3]"),
        (operator.__rshift__, ("split",(0,1)), fgb.Chain("overlay"), "[UNC0]split[L0][UNC2];[UNC1][L0]overlay[UNC3]"),
        (operator.__rshift__, ("split[out]",1), fgb.Chain("overlay"), "[UNC0]split[L0][UNC2];[UNC1][L0]overlay[UNC3]"),
        (operator.__rshift__, ("split[out]", '[out]',None), fgb.Chain("overlay"), "[UNC0]split[L0][UNC2];[L0][UNC1]overlay[UNC3]"),
        (operator.__rshift__, ["scale","fps"], fgb.Chain("hstack"), "[UNC0]scale[L0];[UNC1]fps[L1];[L0][L1]hstack[UNC2]"),
        (operator.__rshift__, fgb.Chain("split"), ["[v1]","[v2]"], "[UNC0]split[v1][v2]"),
        # (operator.__rshift__, fgb.Graph("split[out1][out2]"), ('[out1]', '[over]', "[base][over]overlay"), "split[out1][out2];[base][out1]overlay"),
        # fmt:on
    ],
)
def test_ops(op, lhs, rhs, expected):
    assert op(lhs, rhs).compose() == expected
