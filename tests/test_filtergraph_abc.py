from ffmpegio import filtergraph as fgb
import pytest


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
        (None, (None, None, None), True, True, True, True, False, None, None, None, False),
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


# def next_output_pad(
#         self, pad=None, filter=None, chain=None, chainable_first: bool = False
#     ) -> PAD_INDEX:
# def iter_input_pads(
#         self,
#         pad: int | None = None,
#         filter: int | None = None,
#         chain: int | None = None,
#         *,
#         exclude_chainable: bool = False,
#         chainable_first: bool = False,
#         include_connected: bool = False,
#         exclude_named: bool = False,
#     ) -> Generator[tuple[PAD_INDEX, fgb.Filter]]:
# def iter_output_pads(
#         self,
#         pad: int | None = None,
#         filter: int | None = None,
#         chain: int | None = None,
#         *,
#         exclude_chainable: bool = False,
#         chainable_first: bool = False,
#         include_connected: bool = False,
#         exclude_named: bool = False,
#     ) -> Generator[tuple[PAD_INDEX, fgb.Filter, PAD_INDEX | None]]:
# def iter_input_labels(
#         self, exclude_stream_specs: bool = False
#     ) -> Generator[tuple[str, PAD_INDEX]]:
# def iter_output_labels(self) -> Generator[tuple[str, PAD_INDEX]]:
# def get_label(
#         self,
#         input: bool = True,
#         index: PAD_INDEX | None = None,
#         inpad: PAD_INDEX | None = None,
#         outpad: PAD_INDEX | None = None,
#     ) -> str | None:
# def add_label(
#         self,
#         label: str,
#         inpad: PAD_INDEX | Sequence[PAD_INDEX] = None,
#         outpad: PAD_INDEX = None,
#         force: bool = None,
#     ) -> fgb.Graph:
# def __getitem__(self, key): ...
# def __str__(self):
# def __repr__(self) -> str: ...
# def __add__(self, other: FilterGraphObject | str) -> fgb.Chain | fgb.Graph:
# def __radd__(self, other: FilterGraphObject | str) -> fgb.Chain | fgb.Graph:
# def __mul__(self, __n: int) -> fgb.Graph:
# def __rmul__(self, __n: int) -> fgb.Graph:
# def __or__(self, other: FilterGraphObject | str) -> fgb.Graph:
# def __ror__(self, other: FilterGraphObject | str) -> fgb.Graph:
# def __rshift__(
#         self,
#         other: (
#             FilterGraphObject
#             | str
#             | tuple[FilterGraphObject, PAD_INDEX | str]
#             | tuple[FilterGraphObject, PAD_INDEX | str, PAD_INDEX | str]
#             | list[
#                 FilterGraphObject
#                 | str
#                 | tuple[FilterGraphObject, PAD_INDEX | str]
#                 | tuple[FilterGraphObject, PAD_INDEX | str, PAD_INDEX | str]
#             ]
#         ),
#     ) -> fgb.Graph:
# def __rrshift__(
#         self,
#         other: (
#             FilterGraphObject
#             | str
#             | tuple[PAD_INDEX | str, FilterGraphObject]
#             | tuple[PAD_INDEX | str, PAD_INDEX | str, FilterGraphObject]
#             | list[
#                 FilterGraphObject
#                 | str
#                 | tuple[PAD_INDEX | str, FilterGraphObject]
#                 | tuple[PAD_INDEX | str, PAD_INDEX | str, FilterGraphObject]
#             ]
#         ),
#     ) -> fgb.Graph:
# def _chain(
#         self,
#         on_left: bool,
#         other: fgb.abc.FilterGraphObject,
#         chain_id: int,
#         other_chain_id: int,
#     ) -> fgb.Chain | fgb.Graph:
# def resolve_pad_index(
#         self,
#         index_or_label: PAD_INDEX | str | None,
#         *,
#         is_input: bool = True,
#         chain_id_omittable: bool = False,
#         filter_id_omittable: bool = False,
#         pad_id_omittable: bool = False,
#         resolve_omitted: bool = True,
#         chain_fill_value: int | None = None,
#         filter_fill_value: int | None = None,
#         pad_fill_value: int | None = None,
#         chainable_first: bool = False,
#     ) -> PAD_INDEX:
# def _input_pad_is_available(self, index: tuple[int, int, int]) -> bool:
# def _output_pad_is_available(self, index: tuple[int, int, int]) -> bool:
# def _check_partial_pad_index(
#     self, index: tuple[int | None, int | None, int | None], is_input: bool
# ) -> bool:
# def _input_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
# def _output_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:

# def _attach(
#         self,
#         is_input: bool,
#         other: fgb.abc.FilterGraphObject,
#         index: PAD_INDEX | list[PAD_INDEX],
#         other_index: PAD_INDEX | list[PAD_INDEX],
#     ) -> fgb.Chain | fgb.Graph:
