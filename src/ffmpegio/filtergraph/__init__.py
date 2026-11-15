"""ffmpegio.filtergraph module - FFmpeg filtergraph classes

    Arithmetic Filtergraph Construction
    ===================================

    .. list-table:: Supported Arithmetic Operators
   :widths: 15 10 30
   :header-rows: 1

   ------------------------------  ------------------------------------------------------------
   Operation                       Description  Related Methods
   ------------------------------  ------------------------------------------------------------
   :code:`+` operator                    Chaining/join operator, supports scalar expansion
   :code:`Filter + Filter -> Chain`      Create a filterchain from 2 filters
   :code:`Chain  + Filter -> Chain`      Append filter to filterchain
   :code:`Filter + Chain  -> Chain`      Prepend filter to filterchain
   :code:`Chain  + Chain  -> Chain`      Concatenate filterchains
   :code:`Filter + Graph  -> Graph`      Prepend filer to first available input of each chain
   :code:`Graph  + Filter -> Graph`      Append filter to first available output of each chain
   :code:`Graph  + Chain  -> Graph`      Append filterchain to first available input of each chain
   :code:`Chain  + Graph  -> Graph`      Prepend filterchain to first available output of each chain
   :code:`Graph  + Graph  -> Graph`      Join 2 graphs by matching their inputs and outputs in order

   :code:`*` operator                    Multiplicate-n-stacking operator
   :code:`Filter * int    -> Graph`      Stacking the filters (int) times
   :code:` Chain * int    -> Graph`      Stacking the chain (int) times
   :code:` Graph * int    -> Graph`      Stacking the input graph (int) times

   :code:`|` operator                    Stacking operator
   :code:`Filter | Filter -> Graph`      Stacking the filters
   :code:` Chain | Filter -> Graph`      Stacking chain and filter
   :code:`Filter | Chain  -> Graph`      Stacking filter and chain
   :code:` Chain | Chain  -> Graph`      Stacking the filterchains
   :code:`Filter | Graph  -> Graph`      Prepend filter as a new chain
   :code:` Graph | Filter -> Graph`      Appendd filter as a new chain
   :code:` Graph | Chain  -> Graph`      Stack graph and chain
   :code:` Chain | Graph  -> Graph`      Stack
   :code:` Graph | Graph  -> Graph`      Stack filtergraphs

   left :code:`>>` operator              Input labeling or attach input filter/chain
   :code:`      str >> Filter -> Graph`  Label first available input pad*
   :code:`      str >> Chain  -> Graph`  Label first available input pad*
   :code:`      str >> Graph  -> Graph`  Label first available chainable input pad*
   :code:`   Filter >> Graph  -> Graph`  Attach filter output to first available input pad
   :code:`    Chain >> Graph  -> Graph`  Adding Chain to itself int times
   :code:`(_,Index) >> Filter -> Graph`  Specify input pad
   :code:`(_,Index) >> Chain  -> Graph`  Specify input pad of the first filter
   :code:`(_,Index) >> Graph  -> Graph`  Specify input pad

   right :code:`>>` operator             Output labeling or attach output filter/chain
   :code:`Filter >> str       -> Graph`  Label first available output pad*
   :code:` Chain >> str       -> Graph`  Label first available output pad*
   :code:` Graph >> str       -> Graph`  Label first available chainable output pad*
   :code:` Graph >> Filter    -> Graph`  Attach filter to the first
   :code:` Graph >> Chain     -> Graph`  Adding Chain to itself int times
   :code:`Filter >> (Index,_) -> Graph`  Specify output pad
   :code:` Chain >> (Index,_) -> Graph`  Specify output pad
   :code:` Graph >> (Index,_) -> Graph`  Specify output pad
   ------------------------------  ------------------------------------------------------------

Filter Pad Labeling
===================

`str >> Filter/Chain/Graph` and :code:`Filter/Chain/Graph >> str` operations can be
used to set input and output labels, respectively. The labels must be specified
in square brackets as in the same manner as FFmpeg filtergraph specification.

.. code-block::python

    fg = '[in]' >> Filter('scale',0.5,-1) >> '[out]'

The brackets are required to distinguish labels from str expressions of filter,
chain, and graph. For example, the following expression chains :code:`scale` and
`setsar` filters:

.. code-block::python

    fg = '[in]' >> Filter('scale',0.5,-1) + 'setsar=1/1' >> '[out]'

Filter Pad Indexing
===================

Both input and output filter pads can be specified in a number of ways:

    ---------------------  -----------------------------------------------------------------------
    Syntax                 Description
    ---------------------  -----------------------------------------------------------------------
    int n                  Specifies the n-th pad of the first available filter
    (int m, int n)         Specifies the n-th pad of the m-th filter of the first available chain
    (int k, int m, int n)  Specifies the n-th pad of the m-th filter of the k-th chain
    str label              Specifies the pad associated with the link label (no bracket necessary)
    ---------------------  -----------------------------------------------------------------------

 Except for the label indexing, which is a Graph specific feature, all the indexing syntax may be
 used by :py:class:`Filter`, :py:class:`Chain`, or :py:class:`Graph` class instances. An irrelevant field (e.g., chain or filter
 indexing for a :py:class:`Filter` instance) will be ignored. Standard negative-number indexing is supported.

"""

from __future__ import annotations

from .. import path
from ..caps import filters as list_filters
from . import abc, presets
from .build import connect, join, stack
from .chains import Chain
from .convert import (
    as_filter,
    as_filterchain,
    as_filtergraph,
    as_filtergraph_object,
    as_filtergraph_object_like,
    atleast_filterchain,
)
from .exceptions import (
    FiltergraphConversionError,
    FiltergraphInvalidExpression,
    FiltergraphInvalidIndex,
    FiltergraphPadNotFoundError,
)
from .filters import Filter
from .graphs import Graph
from .graph_links import GraphLinks

# chain | filter | pad

__all__ = [
    "abc",
    "presets",
    "as_filter",
    "as_filterchain",
    "as_filtergraph",
    "as_filtergraph_object",
    "as_filtergraph_object_like",
    "atleast_filterchain",
    "connect",
    "join",
    "attach",
    "stack",
    "concatenate",
    "Filter",
    "Chain",
    "Graph",
    "GraphLinks",
    "FiltergraphInvalidIndex",
    "FiltergraphPadNotFoundError",
    "FiltergraphConversionError",
    "FiltergraphInvalidExpression",
]


# dict: stores filter construction functions
_filters = {}


def __getattr__(name):
    """Dynamically implement constructor functions for all available FFmpeg filters"""
    func = _filters.get(name, None)
    if func is None:
        try:
            notfound = name not in list_filters()
        except path.FFmpegNotFound:
            notfound = True

        if notfound:
            raise AttributeError(
                f"{name} is neither a valid ffmpegio.filtergraph module's instance attribute "
                "nor a valid FFmpeg filter name."
            )

        def func(*args, filter_id=None, **kwargs):
            return Filter(name, *args, filter_id=filter_id, **kwargs)

        func.__name__ = name
        func.__doc__ = path.ffmpeg(
            f"-hide_banner -h filter={name}", universal_newlines=True, stdout=path.PIPE
        ).stdout
        _filters[name] = func

    return func


# TODO
# def validate_input_filtergraph(fg):

#     for idx, f, _ in fg.iter_output_pads():
#         label = fg.get_label(outpad=idx)
#         if label is None:  # '[Out0]'
#             if 0 in outlabels:
#                 raise ValueError(
#                     "Invalid input filtergraph. Only one unlabeled output allowed."
#                 )
#             st = 0
#         elif m := re.match(r"out(\d)+$", label):
#             st = int(m[1])
#         else:
#             raise ValueError(
#                 'Input filtergraph must be labelled as "outN" where N is a nonnegative integer, starting at 0.'
#             )
#         outlabels[st] = f.get_pad_media_type(port="out", pad_id=idx[-1])
#     if (n := len(outlabels)) != max(outlabels) + 1:
#         raise ValueError("Invalid input filtergraph. Missing output label(s).")
