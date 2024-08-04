from __future__ import annotations

from typing import Literal
from collections.abc import Generator, Sequence

from .typing import PAD_INDEX

from .exceptions import FiltergraphConversionError, FiltergraphInvalidExpression
from .. import filtergraph as fgb

def connect(
    left: fgb.abc.FilterGraphObject | str,
    right: fgb.abc.FilterGraphObject | str,
    from_left: PAD_INDEX | str | list[PAD_INDEX | str],
    to_right: PAD_INDEX | str | list[PAD_INDEX | str],
    chain_siso: bool = True,
    replace_sws_flags: bool | None = None,
) -> fgb.Graph:
    """stack another Graph and make connection from left to right

    :param right: other filtergraph
    :param from_left: output pad ids or labels of this fg
    :param to_right: input pad ids or labels of the `right` fg
    :param chain_siso: True to chain the single-input single-output connection, default: True
    :param replace_sws_flags: True to use `right` sws_flags if present,
                                False to drop `right` sws_flags,
                                None to throw an exception (default)
    :return: new filtergraph object

    * link labels may be auto-renamed if there is a conflict

    """

    # make sure right is a Graph object
    left = fgb.as_filtergraph_object(left)
    right = fgb.as_filtergraph_object(right)

    if not isinstance(from_left, list):
        from_left = [from_left]
    if not isinstance(to_right, list):
        to_right = [to_right]

    if len(from_left) != len(to_right):
        raise ValueError(
            f"the number of pads in {from_left=} and {to_right=} must match."
        )

    links = [
        (
            left._resolve_pad_index(l, is_input=False),
            right._resolve_pad_index(r, is_input=True),
        )
        for l, r in zip(from_left, to_right)
    ]

    out = left._connect(right, links, chain_siso, replace_sws_flags)
    if out == NotImplemented:
        out = right._rconnect(right, links, chain_siso, replace_sws_flags)
    return out

def join(
    left,
    right: fgb.abc.FilterGraphObject | str,
    how: Literal["chainable", "per_chain", "all", "auto"] = "per_chain",
    n_links: int = -1,
    match_scalar: bool = False,
    ignore_labels: bool = False,
    chain_siso: bool = True,
    replace_sws_flags: bool = None,
) -> fgb.Graph | None:
    """append another Graph object and auto-connect its inputs to the outputs of this filtergraph

    :param left: source filtergraph object
    :param right: sink filtergraph object
    :param how: method on how to mate input and output, defaults to "per_chain".

        ===========  ===================================================================
        'chainable'  joins only chainable input pads and output pads.
        'per_chain'  joins one pair of first available input pad and output pad of each
                        mating chains. Source and sink chains are ignored.
        'all'        joins all input pads and output pads
        'auto'       tries 'per_chain' first, if fails, then tries 'all'.
        ===========  ===================================================================

    :param n_links: number of left output pads to be connected to the right input pads, default: 0 
                    (all matching links). If ``how=='per_chain'``, ``n_links`` connections are made 
                    per chain.
    :param match_scalar: True to multiply left if SO-MI connection or right if MO-SI connection
                         to single-ended entity to the other, defaults to False
    :param ignore_labels: True to pair pads w/out checking pad labels, default: True
    :param chain_siso: True to chain the single-input single-output connection, default: True
    :param replace_sws_flags: True to use other's sws_flags if present,
                                False to ignore other's sws_flags,
                                None to throw an exception (default)
    :return: Graph with the appended filter chains or None if inplace=True.
    """

    # make sure right is a Graph, Chain, or Filter object
    left = fgb.as_filtergraph(left)
    right = fgb.as_filtergraph(right)

    unlabeled_only = not ignore_labels

    if how == "chainable":
        left_pads = list(
            left.iter_output_pads(
                chainable_only=True, unlabeled_only=unlabeled_only
            )
        )
        right_pads = list(
            right.iter_input_pads(
                chainable_only=True, unlabeled_only=unlabeled_only
            )
        )
        if match_scalar:
            nleft = len(left_pads)
            nright = len(right_pads)
            if nleft == 1 and nright > 1:
                left = (left, left_pads) * nright
            elif nright == 1 and nleft > 1:
                right = (right, right_pads) * nleft

    elif how == "per_chain":
        left_pads = [
            (i, *p)
            for i, c in left.iter_chains(skip_if_no_output=True)
            for p in c.iter_output_pads()
        ]
        right_pads = [
            (i, *p)
            for i, c in right.iter_chains(skip_if_no_input=True)
            for p in c.iter_input_pads()
        ]
    elif how == "all":
        left_pads = list(left.iter_output_pads())
        right_pads = list(right.iter_input_pads())
    elif how == "auto":
        # auto-mode, 1-deep recursion
        try:
            return left.join(
                right,
                "per_chain",
                match_scalar,
                ignore_labels,
                chain_siso,
                replace_sws_flags,
            )
        except:
            return left.join(
                right,
                "all",
                match_scalar,
                ignore_labels,
                chain_siso,
                replace_sws_flags,
            )

    else:
        raise ValueError(f"{how=} is an unknown matching method")

    if match_scalar or chain_siso or how == "per_chain":
        nout = left.get_num_outputs()
        nin = left.get_num_inputs()
        single_out = nout == 1
        single_in = nin == 1

    # list all the unconnected output pads of left fg
    # [(index, label, filter)]
    src_info = tuple(left._iter_io_pads(False, how, ignore_labels))

    # list all the unconnected input pads of right fg
    dst_info = tuple(right._iter_io_pads(True, how, ignore_labels))

    # to join, the number of pads must match
    nsrc = len(src_info)
    ndst = len(dst_info)

    if nsrc != ndst:

        if match_scalar and ndst == 1:
            # multiply right to match left
            right = right * nsrc
            dst_info = right._iter_io_pads(True, how)
        elif match_scalar and nsrc == 1:
            # multiply left to match right
            left = left * ndst
            src_info = left._iter_io_pads(False, how)
        else:
            raise FiltergraphMismatchError(nsrc, ndst)

    return left.connect(
        right,
        [index for index, *_ in src_info],
        [index for index, *_ in dst_info],
        chain_siso,
        replace_sws_flags,
    )

def attach(
    left,
    right: fgb.abc.FilterGraphObject | str,
    left_on: PAD_INDEX | None = None,
    right_on: PAD_INDEX | None = None,
):
    """attach an output pad to right's input pad

    :param right: output filterchain to be attached
    :type right: Chain or Filter
    :param left_on: pad_index, specify the pad on left, default to None (first available)
    :type left_on: int or str, optional
    :param right_on: pad index, specifies which pad on the right graph, defaults to None (first available)
    :type right_on: int or str, optional
    :return: new filtergraph object
    :rtype: Graph

    """

    right = fgb.as_filtergraph_object(right)
    right_on = right._resolve_pad_index(
        right_on,
        is_input=True,
        chain_id_omittable=True,
        filter_id_omittable=True,
        pad_id_omittable=True,
    )
    left_on = left._resolve_pad_index(
        left_on,
        is_input=False,
        chain_id_omittable=True,
        filter_id_omittable=True,
        pad_id_omittable=True,
    )
    return left._connect(right, [(left_on, right_on)], chain_siso=True)
