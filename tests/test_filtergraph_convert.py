import pytest

from ffmpegio import filtergraph as fgb


@pytest.mark.parametrize("filter_spec", ["scale", fgb.scale()])
def test_as_filter(filter_spec):
    assert isinstance(fgb.as_filter(filter_spec), fgb.Filter)


@pytest.mark.parametrize(
    "filter_spec,copy",
    [
        ("scale,fps", True),
        (fgb.Chain("scale,fps"), False),
        (fgb.Chain("scale,fps"), True),
    ],
)
def test_as_filterchain(filter_spec, copy):
    obj = fgb.as_filterchain(filter_spec, copy)
    assert isinstance(obj, fgb.Chain)
    if copy:
        assert id(obj) != id(filter_spec)
    else:
        assert id(obj) == id(filter_spec)


@pytest.mark.parametrize(
    "filter_spec,copy",
    [
        ("scale,fps", True),
        (fgb.Graph("scale,fps"), False),
        (fgb.Graph("scale,fps"), True),
    ],
)
def test_as_filtergraph(filter_spec, copy):
    obj = fgb.as_filtergraph(filter_spec, copy)
    assert isinstance(obj, fgb.Graph)
    if copy:
        assert id(obj) != id(filter_spec)
    else:
        assert id(obj) == id(filter_spec)


@pytest.mark.parametrize(
    "filter_spec,copy,res",
    [
        ("", True, fgb.Chain),
        ("scale", True, fgb.Filter),
        ("scale,fps", True, fgb.Chain),
        ("scale;fps", True, fgb.Graph),
        (fgb.scale(), False, fgb.Filter),
        (fgb.Chain("scale,fps"), False, fgb.Chain),
        (fgb.Graph("scale,fps"), False, fgb.Graph),
        (fgb.Graph("scale,fps"), True, fgb.Graph),
    ],
)
def test_as_filtergraph_object(filter_spec, copy, res):
    obj = fgb.as_filtergraph_object(filter_spec, copy)
    assert isinstance(obj, res)
    if copy:
        assert id(obj) != id(filter_spec)
    else:
        assert id(obj) == id(filter_spec)


@pytest.mark.parametrize(
    "filter_spec,like,copy",
    [
        (fgb.Chain("scale,fps"), fgb.Chain("scale,fps"), False),
        (fgb.Chain("scale,fps"), fgb.Chain("scale,fps"), True),
        (fgb.Chain("scale,fps"), fgb.Graph("scale,fps"), True),
    ],
)
def test_as_filtergraph_object_like(filter_spec, like, copy):
    obj = fgb.as_filtergraph_object_like(filter_spec, like, copy)
    assert isinstance(obj, type(like))
    if copy:
        assert id(obj) != id(filter_spec)
    else:
        assert id(obj) == id(filter_spec)


@pytest.mark.parametrize(
    "filter_spec,copy,res",
    [
        ("scale", True, fgb.Chain),
        ("[in]scale[out]", True, fgb.Graph),
        ("sws_flags=linear;scale", True, fgb.Graph),
        ("scale;fps", True, fgb.Graph),
        (fgb.scale(), True, fgb.Chain),
        (fgb.Chain("scale,fps"), False, fgb.Chain),
        (fgb.Chain("scale,fps"), True, fgb.Chain),
        (fgb.Graph("scale,fps"), False, fgb.Graph),
        (fgb.Graph("scale,fps"), True, fgb.Graph),
    ],
)
def test_atleast_filterchain(filter_spec, copy, res):

    obj = fgb.atleast_filterchain(filter_spec, copy)
    assert isinstance(obj, res)
    if copy:
        assert id(obj) != id(filter_spec)
    else:
        assert id(obj) == id(filter_spec)
