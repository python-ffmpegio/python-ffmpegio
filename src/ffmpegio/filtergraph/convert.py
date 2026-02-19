from __future__ import annotations

from .. import filtergraph as fgb
from . import utils as filter_utils


def as_filter(filter_spec: str | fgb.abc.FilterGraphObject) -> fgb.Filter:
    """convert the input to a filter

    :param filter_spec: filtergraph expression or object.
    :return: ``Filter`` object interpretation of ``filter_spec``. No copy is performed if the input is
             already a ``Filter`` and ``copy=False``.

    If the input is a ``Chain`` or ``Graph`` object with more than one filter element, this function
    will raise a ``FiltergraphConversionError`` exception.

    If the input expression could not be parsed, ``FiltergraphInvalidExpression`` will be raised.
    """
    return (
        filter_spec if isinstance(filter_spec, fgb.Filter) else fgb.Filter(filter_spec)
    )


def as_filterchain(
    filter_specs: str | fgb.abc.FilterGraphObject, copy: bool = False
) -> fgb.Chain:
    """Convert the input to a filter chain

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: ``Chain`` object interpretation of ``filter_spec``. No copy is performed if the input is
             already a ``Chain`` and ``copy=False``.

    If the input is a ``Graph`` object with more than one filter chain, this function
    will raise a ``FiltergraphConversionError`` exception.

    If the input expression could not be parsed, ``FiltergraphInvalidExpression`` will be raised.
    """

    return (
        filter_specs
        if not copy and isinstance(filter_specs, fgb.Chain)
        else fgb.Chain(filter_specs)
    )


def as_filtergraph(
    filter_specs: str | fgb.abc.FilterGraphObject, copy: bool = False
) -> fgb.Graph:
    """Convert the input to a filter graph

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: ``Graph`` object interpretation of ``filter_spec``. No copy is performed if the input is
             already a ``Graph`` and ``copy=False``.

    If the input expression could not be parsed, ``FiltergraphInvalidExpression`` will be raised.
    """
    return (
        filter_specs
        if not copy and isinstance(filter_specs, fgb.Graph)
        else fgb.Graph(filter_specs)
    )


def as_filtergraph_object(
    filter_specs: str | fgb.abc.FilterGraphObject, copy: bool = False
) -> fgb.abc.FilterGraphObject:
    """Convert the input to a filter graph object

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: Depending on the complexity of the ``filter_spec``, ``Filter``,
             ``Chain``, or ``Graph`` object interpretation of ``filter_spec``.
             No copy is performed if the input is already a ``Graph`` and ``copy=False``.
    """

    if not filter_specs:
        return fgb.Chain()

    if isinstance(filter_specs, (fgb.Filter, fgb.Chain, fgb.Graph)):
        return type(filter_specs)(filter_specs) if copy else filter_specs

    specs, links, sws_flags = filter_utils.parse_graph(filter_specs, False)
    return (
        fgb.Graph(specs, links, sws_flags)
        if links or sws_flags or len(specs) > 1
        else fgb.Filter(specs[0][0])
        if len(specs[0]) == 1
        else fgb.Chain(specs[0])
    )


def as_filtergraph_object_like(
    filter_specs: str | fgb.abc.FilterGraphObject,
    like: fgb.abc.FilterGraphObject,
    copy: bool = False,
) -> fgb.abc.FilterGraphObject:
    """Try to convert input filtergraph spec to match the type of like object

    :param filter_spec: filtergraph expression or object.
    :param like: reference filtergraph object to match the type
    :param copy: ``True`` to copy if the input is a ``Chain`` or a ``Graph``.
        ``Filter`` objects are immutable so they are always returned as is.
    :return: Filtergraph object of the same type as ``like`` object.
        No copy is performed if the input is already a ``Graph`` and ``copy=False``.
    """
    otype = type(like)
    return (
        filter_specs
        if not copy and isinstance(filter_specs, otype)
        else otype(filter_specs)
    )


def atleast_filterchain(
    filter_specs: str | fgb.abc.FilterGraphObject, copy: bool = False
) -> fgb.Chain | fgb.Graph:
    """Convert the input to a filter graph object

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: Depending on the complexity of the ``filter_spec``, ``Filter``,
             ``Chain``, or ``Graph`` object interpretation of ``filter_spec``.
             No copy is performed if the input is already a ``Graph`` and ``copy=False``.
    """

    if isinstance(filter_specs, (fgb.Chain, fgb.Graph)):
        return type(filter_specs)(filter_specs) if copy else filter_specs

    if isinstance(filter_specs, fgb.Filter):
        return fgb.Chain(filter_specs)

    # str input
    specs, links, sws_flags = filter_utils.parse_graph(filter_specs, False)
    return (
        fgb.Graph(specs, links, sws_flags)
        if links or sws_flags or len(specs) > 1
        else fgb.Chain(specs[0])
    )
