from ffmpegio import ffmpegprocess, filtergraph as fgb

from pprint import pprint
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
        (fgb.Filter, "color", None, None, None, False, -1),
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
# def _resolve_pad_index(
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


def test_iter_io_pads():
    fg = fgb.Graph(
        "color;scale,pad[l1]; crop,pad[l2]; overlay; [l1]overlay; pad,overlay; trim,[l2]overlay"
    )
    print(fg)
    pprint(tuple(fg._iter_io_pads(True, "all")))
    pprint(tuple(fg._iter_io_pads(True, "chainable")))
    pprint(tuple(fg._iter_io_pads(True, "per_chain")))


def test_resolve_index():
    fg = fgb.Graph(
        "color;scale,pad[l1]; crop,pad[l2]; overlay; [l1]overlay; pad,overlay[l3]; trim,[l2]overlay,split=3[l4];[l3][l4]overlay"
    )
    fg.add_label("in", dst=(2, 0, 0))
    print(fg)
    pprint(tuple(fg._iter_io_pads(True, "all")))
    # pprint(tuple(fg._iter_io_pads(False, "all")))
    assert fg._resolve_index(True, 0) == (1, 0, 0)

    assert fg._resolve_index(True, None) == (1, 0, 0)
    assert fg._resolve_index(True, "in") == (2, 0, 0)
    assert fg._resolve_index(True, "[in]") == (2, 0, 0)
    assert fg._resolve_index(True, 1) == (3, 0, 1)
    assert fg._resolve_index(True, (1, None)) == (5, 1, 0)

    # pprint(fg._resolve_index(False, 0))
    # pprint(fg._resolve_index(False, 1))


@pytest.mark.parametrize(
    "fg,fc,left_on,right_on,out",
    [
        ("fps;crop", "trim", None, None, "[UNC0]fps,trim[UNC1];[UNC2]crop[UNC3]"),
        ("fps[out];crop", "trim", None, None, "fps,trim;crop"),
        ("fps;crop", "trim", (1, 0, 0), None, "fps;crop,trim"),
        ("fps;crop[out]", "trim", "out", None, "fps;crop,trim"),
        (
            fgb.Graph(["fps", "crop"], {"out": ((None, (1, 0, 0)), (0, 0, 0))}),
            "trim",
            "out",
            None,
            None,
        ),
        (
            fgb.Graph(["fps", "crop"], {"out": ((None, None), (0, 0, 0))}),
            "trim",
            "out",
            None,
            "fps,trim;crop",
        ),
        ("fps[L];[L]crop", "trim", None, None, "fps[L];[L]crop,trim"),
        ("split=2[C];[C]crop", "trim", None, None, "split=2[C][L0];[C]crop;[L0]trim"),
        (
            "split=2[C][out];[C]crop",
            "trim",
            "out",
            None,
            "split=2[C][out];[C]crop;[out]trim",
        ),
    ],
)
def test_attach(fg, fc, left_on, right_on, out):
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg = fg.attach(fc, left_on, right_on)
    else:
        fg = fg.attach(fc, left_on, right_on)
        assert str(fg) == out


@pytest.mark.parametrize(
    "fg,fc,left_on,skip_named,out",
    [
        ("fps;crop", "trim", None, None, "trim,fps;crop"),
        ("[in]fps;crop", "trim", None, None, "trim,fps;crop"),
        ("fps;crop", "trim", (1, 0, 0), None, "trim,crop;fps"),
        ("fps;[in]crop", "trim", "in", None, "trim,crop;fps"),
        ("[L]fps;crop[L]", "trim", None, None, "trim,crop[L];[L]fps"),
        ("[C]overlay;crop[C]", "trim", None, None, "trim[L0];[C][L0]overlay;crop[C]"),
        (
            "[C][in]overlay;crop[C]",
            "trim",
            "in",
            None,
            "trim[in];[C][in]overlay;crop[C]",
        ),
    ],
)
def test_rattach(fg, fc, left_on, skip_named, out):
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg = fg.rattach(fc, left_on, skip_named)
    else:
        fg = fg.rattach(fc, left_on, skip_named)
        assert str(fg) == out


@pytest.mark.parametrize(
    "fg, other, auto_link, replace_sws_flags, out",
    [
        ("fps;crop", "trim;scale", False, None, "fps;crop;trim;scale"),
        ("fps;crop", "trim,scale", False, None, "fps;crop;trim,scale"),
        (
            "[la]fps;crop[lb]",
            "[lb]trim;scale[la]",
            False,
            None,
            "[la1]fps;crop[lb1];[lb2]trim;scale[la2]",
        ),
        (
            "[la]fps;crop[lb]",
            "[lb]trim;scale[la]",
            True,
            None,
            "[la]fps;crop[lb];[lb]trim;scale[la]",
        ),
        ("sws_flags=w=200;fps;crop", "sws_flags=h=400;trim;scale", False, None, None),
        (
            "sws_flags=w=200;fps;crop",
            "sws_flags=h=400;trim;scale",
            False,
            False,
            "sws_flags=w=200;fps;crop;trim;scale",
        ),
        (
            "sws_flags=w=200;fps;crop",
            "sws_flags=h=400;trim;scale",
            False,
            True,
            "sws_flags=h=400;fps;crop;trim;scale",
        ),
    ],
)
def test_stack(fg, other, auto_link, replace_sws_flags, out):
    # other, auto_link=False, replace_sws_flags=None,
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg = fg.stack(other, auto_link, replace_sws_flags)
    else:
        fg = fg.stack(other, auto_link, replace_sws_flags)
        assert str(fg) == out


@pytest.mark.parametrize(
    "fg, id, out",
    [
        # fmt: off
        ("fps;crop", (0,0,0), ((0,0,0),None)),
        ("fps;crop", (1,0,0), ((1,0,0),None)),
        ("fps;crop", (0,1,0), None),
        ("fps;crop", 'fake', None),
        ("[la]fps;crop[lb]", 'la', ((0,0,0),'la')),
        ("[la]fps;crop[lb]", 'lb', None),
        ("[a]fps;[a]crop", 'a', None),
        ("[0:v]fps;[0:v]crop", (0,0,0), None),
        # fmt: on
    ],
)
def test_get_input_pad(fg, id, out):
    # other, auto_link=False, replace_sws_flags=None,
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg.get_input_pad(id)
    else:
        assert fg.get_input_pad(id) == out


@pytest.mark.parametrize(
    "fg, id, out",
    [
        # fmt: off
        ("fps;crop", (0,0,0), ((0,0,0),None)),
        ("fps;crop", (1,0,0), ((1,0,0),None)),
        ("fps;crop", (0,1,0), None),
        ("fps;crop", 'fake', None),
        ("[la]fps;crop[lb]", 'lb', ((1,0,0),'lb')),
        ("[la]fps;crop[lb]", 'la', None),
        # TODO: test split output case
        # fmt: on
    ],
)
def test_get_output_pad(fg, id, out):
    # other, auto_link=False, replace_sws_flags=None,
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg.get_output_pad(id)
    else:
        assert fg.get_output_pad(id) == out


@pytest.mark.parametrize(
    "fg, r, to_l,to_r,chain, out",
    [
        # fmt: off
        ("[a]fps;crop[b]", "[c]trim;scale[d]", ['b'], ['c'], None, "[a]fps;crop[b];[b]trim;scale[d]"),
        ("[la]fps;crop[lb]", "[lb]trim;scale[la]", ['lb'], ['lb'], None, "[la1]fps;crop[lb];[lb]trim;scale[la2]"),
        ("[a]fps;crop[b]", "[c]trim;scale[d]", ['b'], ['c'], True, "[a]fps;crop,trim;scale[d]"),
        # fmt: on
    ],
)
def test_connect(fg, r, to_l, to_r, chain, out):
    # other, auto_link=False, replace_sws_flags=None,
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg = fg.connect(r, to_l, to_r, chain)
    else:
        fg = fg.connect(r, to_l, to_r, chain)
        assert str(fg) == out


@pytest.mark.parametrize(
    "fg, r, how, match_scalar, ignore_labels, out",
    [
        # fmt: off
        ("fps;crop", "trim;scale", None, False, False, "fps,trim;crop,scale"),
        ("[a]fps;crop[b]", "[c]trim;scale[d]", None, False, True, "[a]fps,trim;crop,scale[d]"),
        ("fps;crop", "trim", None, True, False, "fps,trim;crop,trim"),
        ("fps", "trim;crop", None, True, False, "fps,trim;fps,crop"),
        ("fps", "overlay", 'per_chain', False, False, "fps[L0];[L0]overlay"),
        ("fps", "overlay", 'all', True, False, "fps[L0];fps[L1];[L0][L1]overlay"),
        ("fps", "overlay", 'chainable', True, False, "fps[L0];[L0]overlay"),
        # fmt: on
    ],
)
def test_join(fg, r, how, match_scalar, ignore_labels, out):
    # other, auto_link=False, replace_sws_flags=None,
    fg = fgb.Graph(fg)
    if out is None:
        with pytest.raises(fgb.Graph.Error):
            fg = fg.join(r, how, match_scalar, ignore_labels)
    else:
        fg = fg.join(r, how, match_scalar, ignore_labels)
        assert str(fg) == out


# @pytest.mark.parametrize(
#     "f1e,f2",
#     [
#         ("fps", "trim"),
#         ("fps", "trim,crop"),
#         ("fps", "trim;crop"),
#         ("fps,scale", "trim"),
#         ("fps,scale", "trim,crop"),
#         ("fps,scale", "trim;crop"),
#         ("fps;scale", "trim"),
#         ("fps;scale", "trim,crop"),
#         ("fps;scale", "trim;crop"),
#     ],
# )
def test_filter_arithmetics():
    fg1 = fgb.trim() + fgb.crop()
    assert isinstance(fg1, fgb.Chain)
    assert str(fg1) == "trim,crop"

    fg2 = fgb.fps() | fgb.scale()
    assert isinstance(fg2, fgb.Graph)
    assert str(fg2) == "fps;scale"

    fg3 = fgb.setpts() * 3
    assert isinstance(fg3, fgb.Graph)
    assert str(fg3) == "setpts;setpts;setpts"

    assert str(("[in]" >> fgb.geq()) >> "[out]") == "[in]geq[out]"
    assert str("[in]" >> (fgb.geq() >> "[out]")) == "[in]geq[out]"

    assert (
        str(["[0:v]", "[1:v]"] >> fgb.vstack(inputs=2)) == "[0:v][1:v]vstack=inputs=2"
    )
    assert str(fgb.split(2) >> [(1, "[main]"), "[sub]"]) == "split=2[sub][main]"
    fc = fgb.vstack(inputs=2) + fgb.split(outputs=2)
    assert (
        str([("[0:v]", 1), "[1:v]"] >> fc)
        == "[1:v][0:v]vstack=inputs=2,split=outputs=2"
    )
    assert (
        str(fc >> ["[main]", "[sub]"]) == "vstack=inputs=2,split=outputs=2[main][sub]"
    )
    assert (
        str(["[0:v]", "[1:v]"] >> fgb.Graph(fc) >> [(1, "[main]"), "[sub]"])
        == "[0:v][1:v]vstack=inputs=2,split=outputs=2[main][sub]"
    )

    fg1 = fgb.trim() >> fgb.crop()
    assert str(fg1) == "trim,crop"

    fg1 = "trim" >> fgb.crop()
    assert str(fg1) == "trim,crop"


def test_filter_empty_handling():
    fg1 = fgb.trim() + fgb.crop()
    fg2 = fgb.fps() | fgb.scale()
    fg3 = fgb.Chain()
    fg4 = fgb.Graph()

    assert str(fg3 * 2) == ""
    assert str(fg4 * 2) == ""

    assert str(fg1 + fg3) == "trim,crop"
    assert str(fg1 | fg3) == "trim,crop"

    assert str(fg2 + fg3) == "fps;scale"
    assert str(fg2 | fg3) == "fps;scale"


def test_script():
    fg = fgb.Graph("trim=duration=1")
    with fg.as_script_file() as script, TemporaryDirectory() as dir:
        out = ffmpegprocess.run(
            {
                "inputs": [(path.join("tests", "assets", "sample.mp4"), None)],
                "outputs": [
                    (path.join(dir, "output.mp4"), {"filter_script:v": script})
                ],
            },
        )
    assert not out.returncode


def test_ops():
    assert str(Chain("scale") + "overlay") == "scale[L0];[L0]overlay"
    assert str("scale" + Chain("overlay")) == "scale[L0];[L0]overlay"


if __name__ == "__main__":
    from pprint import pprint

    from ffmpegio.filtergraph import Graph, filter_info, FFmpegioError, list_filters

    for k, v in list_filters().items():
        if v.num_inputs is None or v.num_inputs:
            continue
        info = filter_info(k)
        # print(info.options)
        d = None
        for o in info.options:
            if o.name == "duration" or "duration" in o.aliases:
                d = o.default
                print(f"{k} found {o.name} option with default {d} ")
                break

        if d is None:
            print(
                f"{k} has no apparent duration option:\n{[o.name for o in info.options]}"
            )

    pprint(srcs)
    exit()
    type = "audio"
    expr = "aevalsrc"

    fg = Graph(expr)
    # if len(fg) != 1 or len(fg[0]) != 1:
    #     # multi-filter input filtergraph, cannot take arguments
    #     return expr, args, kwargs

    f = fg[0][0]
    info = filter_info(f.name)
    print(info)
    if info.inputs is not None:
        raise FFmpegioError(f"{f.name} filter is not a source filter")

    opts = info.options

    print(len(opts))
