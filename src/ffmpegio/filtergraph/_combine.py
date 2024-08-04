from __future__ import annotations

from typing import Literal
from collections.abc import Generator, Sequence

from .typing import PAD_INDEX

from .exceptions import FiltergraphMismatchError, FiltergraphInvalidExpression
from .. import filtergraph as fgb


def connect(
    left: fgb.abc.FilterGraphObject | str,
    right: fgb.abc.FilterGraphObject | str,
    from_left: PAD_INDEX | str | list[PAD_INDEX | str],
    to_right: PAD_INDEX | str | list[PAD_INDEX | str],
    chain_siso: bool = True,
    replace_sws_flags: bool | None = None,
) -> fgb.Graph:
    """stack another Graph and make explicit connection from left to right

    :param left: transmitting filtergraph object
    :param right: receiving filtergraph object
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
    n_links: int = 0,
    strict: bool = False,
    match_scalar: bool = False,
    ignore_labels: bool = False,
    chain_siso: bool = True,
    replace_sws_flags: bool = None,
) -> fgb.Graph | None:
    """smart filtergraph connector

    :param left: transmitting filtergraph object
    :param right: receiving filtergraph object
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
    :param strict: True to raise exception if numbers of available pads do not match, default: False
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
            left.iter_output_pads(chainable_only=True, unlabeled_only=unlabeled_only)
        )
        right_pads = list(
            right.iter_input_pads(chainable_only=True, unlabeled_only=unlabeled_only)
        )
        if match_scalar:
            nleft = len(left_pads)
            nright = len(right_pads)
            if nleft == 1 and nright > 1:
                actions = ([left, left_pads] * nright, right)
            elif nright == 1 and nleft > 1:
                right = (left, [right, right_pads] * nleft)
        else:
            ...

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
    left: fgb.abc.FilterGraphObject | str | list[fgb.abc.FilterGraphObject | str],
    right: fgb.abc.FilterGraphObject | str | list[fgb.abc.FilterGraphObject | str],
    left_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
    right_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
) -> fgb.Graph:
    """attach filter(s), chain(s), or label(s) to a filtergraph object

    :param left: input filtergraph object, filtergraph expression, or label, or list thereof
    :param right: output filterchain, filtergraph expression, or label, or list thereof
    :param left_on: pad_index, specify the pad on left, default to None (first available)
    :param right_on: pad index, specifies which pad on the right graph, defaults to None (first available)
    :return: new filtergraph object

    One and only one of ``left`` or ``right`` may be a list or a label.

    If pad indices are not specified, only the first available output/input pad is linked. If the
    primary filtergraph object is ``Filter`` or ``Chain``, the chainable pad (i.e., the last pad) will be
    chosen.

    """

    def check_obj(obj):
        try:
            obj_label = fgb.as_filtergraph_object(obj)
        except FiltergraphInvalidExpression:
            try:
                obj_label = str(obj)
            except:
                raise ValueError(
                    f"{type(obj)} could not be converted to a filtergraph object or a label string."
                )
        return obj_label

    def analyze_fgobj(obj):
        attach_obj = isinstance(obj, list)
        obj = [check_obj(o) for o in obj] if attach_obj else check_obj(obj)
        if attach_obj and any(isinstance(o, fgb.Graph) for o in obj):
            raise ValueError(
                "Filtergraph object list cannot include any Graph object. Only Filter and Chain objects are allowed."
            )

        return obj, (attach_obj or isinstance(obj, str))

    left_objs_labels, attach_left = analyze_fgobj(left)
    right_objs_labels, attach_right = analyze_fgobj(right)

    if not (attach_left or attach_right):
        # no list or label given
        if isinstance(right_objs_labels, (fgb.Filter, fgb.Chain)):
            attach_right = True
            right_objs_labels = [right_objs_labels]
        if not attach_right and isinstance(left_objs_labels, (fgb.Filter, fgb.Chain)):
            attach_left = True
            left_objs_labels = [left_objs_labels]

    if attach_left == attach_right:
        raise ValueError(
            "Both left and right objects are Graphs. One of left or right argument must be a Filter or Chain object."
        )

    n_links = len(left_objs_labels if attach_right else right_objs_labels)

    def make_pidx_list(pidx, attach, name):
        if isinstance(pidx, list):
            out = pidx
        else:
            out = [pidx]
            out = (out * n_links) if attach or pidx is None else out

        if len(out) != n_links:
            raise ValueError(
                f"Number of pad indices given in {name} ({len(out)}) does not match the number of the elements to be attached ({n_links})."
            )

    left_on = make_pidx_list(left_on, attach_left)
    right_on = make_pidx_list(right_on, attach_right)

    return (
        left_objs_labels._attach(right_objs_labels, left_on, right_on)
        if attach_right
        else right_objs_labels._rattach(left_objs_labels, left_on, right_on)
    )
