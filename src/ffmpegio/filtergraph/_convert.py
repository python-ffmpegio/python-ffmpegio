from __future__ import annotations

from ..utils import filter as filter_utils

from .exceptions import FiltergraphConversionError, FiltergraphInvalidExpression
from .typing import FilterGraphObject
from .Filter import Filter
from .Chain import Chain
from .Graph import Graph

def as_filter(filter_spec: str | FilterGraphObject, copy: bool = False) -> Filter:
    """convert the input to a filter

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: ``Filter`` object interpretation of ``filter_spec``. No copy is performed if the input is
             already a ``Filter`` and ``copy=False``.

    If the input is a ``Chain`` or ``Graph`` object with more than one filter element, this function
    will raise a ``FiltergraphConversionError`` exception.

    If the input expression could not be parsed, ``FiltergraphInvalidExpression`` will be raised.
    """
    if isinstance(filter_spec, Graph):
        if len(filter_spec) != 1 and len(filter_spec[0]) != 1:
            raise FiltergraphConversionError(
                "Only a Graph object with a single one-element chain can be downconverted to Filter."
            )
        else:
            return filter_spec[0, 0]
    if isinstance(filter_spec, Chain):
        if len(filter_spec) != 1:
            raise FiltergraphConversionError(
                "Only a Chain object with a single element can be downconverted to Filter."
            )
        else:
            return filter_spec[0][0]

    try:
        return (
            filter_spec
            if not copy and isinstance(filter_spec, Filter)
            else Filter(filter_spec)
        )
    except Exception as exc:
        raise FiltergraphInvalidExpression from exc


def as_filterchain(filter_specs: str | FilterGraphObject, copy: bool = False) -> Chain:
    """Convert the input to a filter chain

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: ``Chain`` object interpretation of ``filter_spec``. No copy is performed if the input is
             already a ``Chain`` and ``copy=False``.

    If the input is a ``Graph`` object with more than one filter chain, this function
    will raise a ``FiltergraphConversionError`` exception.

    If the input expression could not be parsed, ``FiltergraphInvalidExpression`` will be raised.
    """
    if isinstance(filter_specs, Graph):
        if len(filter_specs) != 1:
            raise FiltergraphConversionError(
                "Only a Graph object with a single chain can be downconverted to Chain."
            )
        return Chain(filter_specs[0])

    try:
        return (
            filter_specs
            if not copy and isinstance(filter_specs, Chain)
            else Chain(
                [filter_specs] if isinstance(filter_specs, Filter) else filter_specs
            )
        )
    except Exception as exc:
        raise FiltergraphInvalidExpression from exc


def as_filtergraph(filter_specs: str | FilterGraphObject, copy: bool = False) -> Graph:
    """Convert the input to a filter graph

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: ``Graph`` object interpretation of ``filter_spec``. No copy is performed if the input is
             already a ``Graph`` and ``copy=False``.

    If the input expression could not be parsed, ``FiltergraphInvalidExpression`` will be raised.
    """
    try:
        return (
            filter_specs
            if not copy and isinstance(filter_specs, Graph)
            else Graph(filter_specs)
        )
    except Exception as exc:
        raise FiltergraphInvalidExpression from exc


def as_filtergraph_object(
    filter_specs: str | FilterGraphObject, copy: bool = False
) -> FilterGraphObject:
    """Convert the input to a filter graph object

    :param filter_spec: filtergraph expression or object.
    :param copy: True to copy even if the input is a Filter object.
    :return: Depending on the complexity of the ``filter_spec``, ``Filter``,
             ``Chain``, or ``Graph`` object interpretation of ``filter_spec``.
             No copy is performed if the input is already a ``Graph`` and ``copy=False``.
    """

    if isinstance(filter_specs, (Filter, Chain, Graph)):
        return type(filter_specs)(filter_specs) if copy else filter_specs

    try:
        specs, links, sws_flags = filter_utils.parse_graph(filter_specs)
    except Exception as exc:
        raise FiltergraphInvalidExpression from exc

    return (
        Graph(specs, links, sws_flags)
        if links or sws_flags or len(specs) > 1
        else Filter(specs[0][0]) if len(specs[0]) == 1 else Chain(specs[0])
    )
