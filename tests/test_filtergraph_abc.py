import pytest

from ffmpegio import filtergraph as fgb


# def get_num_pads(self, input: bool) -> int:
# def get_num_inputs(self) -> int:
# def get_num_outputs(self) -> int:
@pytest.mark.parametrize(
    "cls,expr,nin,nout",
    [
        (fgb.Filter, "split=outputs=4", 1, 4),
        (fgb.Filter, "color", 0, 1),
        (fgb.Filter, "anullsink", 1, 0),
        (fgb.Chain, "split=outputs=4,vstack=inputs=4", 4, 4),
        (fgb.Graph, "split=outputs=4[out],[0:v][1:v][2:v]vstack=inputs=4", 1, 4),
        (fgb.Graph, "split=outputs=2[L1][L2];[L1]scale[O1];[L2]scale[O2]", 1, 2),
    ],
)
def test_get_num_pads(cls, expr, nin, nout):
    fg = cls(expr)
    assert fg.get_num_pads(True) == nin
    assert fg.get_num_pads(False) == nout


# def next_input_pad(
#         self, pad=None, filter=None, chain=None, chainable_first: bool = False
#     ) -> PAD_INDEX:


@pytest.mark.parametrize(
    "cls, expr, pad, filter, chain, chainable_first, ret",
    [
        (fgb.Filter, "vstack", None, None, None, False, (0,)),
        (fgb.Filter, "vstack", None, None, None, True, (1,)),
        (fgb.Filter, "vstack", 0, None, None, False, (0,)),
        (fgb.Filter, "vstack", 1, None, None, False, (1,)),
        (fgb.Filter, "vstack", 2, None, None, False, -2),
        (fgb.Filter, "vstack", -1, None, None, False, (1,)),
        (fgb.Filter, "vstack", None, 0, None, False, (0,)),
        (fgb.Filter, "vstack", None, 1, None, False, -2),
        (fgb.Filter, "vstack", None, None, 0, False, (0,)),
        (fgb.Filter, "vstack", None, None, 1, False, -2),
        (fgb.Filter, "vstack", None, None, None, False, (0,)),
        (fgb.Filter, "color", None, None, None, False, None),
        (fgb.Chain, "split,vstack", None, None, None, False, (0, 0)),
        (fgb.Chain, "split,vstack", None, 1, None, False, (1, 0)),
        (fgb.Chain, "split,vstack", None, 1, None, True, (1, 1)),
        # (fgb.Graph, "split=outputs=4[out],[0:v][1:v][2:v]vstack=inputs=4", 1, 4),
        # (fgb.Graph, "split=outputs=2[L1][L2];[L1]scale[O1];[L2]scale[O2]", 1, 2),
    ],
)
def test_next_input_pad(cls, expr, pad, filter, chain, chainable_first, ret):
    fg = cls(expr)
    try:
        assert fg.next_input_pad(pad, filter, chain, chainable_first) == ret
    except StopIteration:
        assert ret == -1
    except fgb.FiltergraphInvalidIndex:
        assert ret == -2


@pytest.mark.parametrize(
    "index_or_label, ret, is_input, chain_id_omittable, filter_id_omittable, pad_id_omittable, resolve_omitted, chain_fill_value, filter_fill_value, pad_fill_value, chainable_first",
    [
        (None, None, True, False, False, False, False, None, None, None, False),
        (
            None,
            (None, None, None),
            True,
            True,
            True,
            True,
            False,
            None,
            None,
            None,
            False,
        ),
        (None, (0, 0, 0), True, True, True, True, True, 0, 0, 0, False),
        (None, (0, 0, 0), True, True, True, True, True, 0, 0, 0, False),
        (None, (0, 0, 0), True, True, True, True, True, None, None, None, False),
        (None, (0, 0, 1), True, True, True, True, True, None, None, None, True),
        # (None, (0, 0, 0), True, True, True, True, True, 0, 0, 0, False),
        (1, (None, None, 1), True, True, True, True, False, None, None, None, False),
        (1, (0, 0, 1), True, True, True, True, True, 0, 0, 0, False),
        (1, (0, 0, 1), True, True, True, True, True, 0, 0, 0, False),
    ],
)
def test_resolve_pad_index(
    index_or_label,
    ret,
    is_input,
    chain_id_omittable,
    filter_id_omittable,
    pad_id_omittable,
    resolve_omitted,
    chain_fill_value,
    filter_fill_value,
    pad_fill_value,
    chainable_first,
):
    fg = fgb.Chain("vstack,split")

    if ret is None:
        with pytest.raises(fgb.FiltergraphPadNotFoundError):
            fg.resolve_pad_index(
                index_or_label,
                is_input=is_input,
                chain_id_omittable=chain_id_omittable,
                filter_id_omittable=filter_id_omittable,
                pad_id_omittable=pad_id_omittable,
                resolve_omitted=resolve_omitted,
                chain_fill_value=chain_fill_value,
                filter_fill_value=filter_fill_value,
                pad_fill_value=pad_fill_value,
                chainable_first=chainable_first,
            )
    else:
        assert (
            fg.resolve_pad_index(
                index_or_label,
                is_input=is_input,
                chain_id_omittable=chain_id_omittable,
                filter_id_omittable=filter_id_omittable,
                pad_id_omittable=pad_id_omittable,
                resolve_omitted=resolve_omitted,
                chain_fill_value=chain_fill_value,
                filter_fill_value=filter_fill_value,
                pad_fill_value=pad_fill_value,
                chainable_first=chainable_first,
            )
            == ret
        )
