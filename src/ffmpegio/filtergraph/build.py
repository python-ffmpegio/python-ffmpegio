from __future__ import annotations

from typing import Literal, get_args
from itertools import islice

from .typing import PAD_INDEX, JOIN_HOW

from .exceptions import FiltergraphMismatchError, FiltergraphInvalidExpression
from .. import filtergraph as fgb

__all__ = ["connect", "join", "attach"]


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

    Notes
    -----

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
        out = right._rconnect(left, links, chain_siso, replace_sws_flags)
    return out


def join(
    left: fgb.abc.FilterGraphObject | str,
    right: fgb.abc.FilterGraphObject | str,
    how: JOIN_HOW = "per_chain",
    n_links: int | Literal["all"] = "all",
    strict: bool = False,
    unlabeled_only: bool = False,
    chain_siso: bool = True,
    replace_sws_flags: bool = None,
) -> fgb.Graph | None:
    """filtergraph auto-connector

    :param left: transmitting filtergraph object
    :param right: receiving filtergraph object
    :param how: method on how to mate input and output, defaults to ``"per_chain"``.

                - ``'chainable'``: joins only chainable input pads and output pads.
                - ``'per_chain'``: joins one pair of first available input pad and output pad of each
                                   mating chains. Source and sink chains are ignored.
                - ``'all'``: joins all input pads and output pads
                - ``'auto'``: tries ``'per_chain'`` first, if fails, then tries ``'all'``.
    :param n_links: number of left output pads to be connected to the right input pads, default: 0
                    (all matching links). If ``how=='per_chain'``, ``n_links`` connections are made
                    per chain.
    :param strict: True to raise exception if numbers of available pads do not match, default: False
    :param unlabeled_only: True to ignore labeled unconnected pads, defaults to False
    :param chain_siso: True to chain the single-input single-output connection, default: True
    :param replace_sws_flags: True to use other's sws_flags if present,
                                False to ignore other's sws_flags,
                                None to throw an exception (default)
    :return: Graph with the appended filter chains or None if inplace=True.
    """

    # auto-mode, 1-deep recursion
    if how == "auto":
        try:
            return join(
                left,
                right,
                "per_chain",
                n_links,
                strict,
                unlabeled_only,
                chain_siso,
                replace_sws_flags,
            )
        except:
            return join(
                left,
                right,
                "all",
                n_links,
                strict,
                unlabeled_only,
                chain_siso,
                replace_sws_flags,
            )

    if how not in get_args(JOIN_HOW):
        raise ValueError(f"{how=} is an unknown matching method")

    # make sure right is a Graph, Chain, or Filter object
    left = fgb.as_filtergraph_object(left)
    right = fgb.as_filtergraph_object(right)

    iter_kws = {"unlabeled_only": unlabeled_only, "full_pad_index": True}
    if how == "chainable":
        iter_kws["chainable_only"] = True

    if n_links == "all" or n_links < 0:
        n_links = 0

    def create_links(it_left, it_right):
        if n_links:
            it_left = islice(it_left, n_links)
            it_right = islice(it_right, n_links)

        it_left = (v[0] for v in it_left)
        it_right = (v[0] for v in it_right)

        try:
            return list(zip([*it_left], [*it_right], strict=strict))
        except ValueError:
            raise ValueError(
                f"Available pads of left and right filtergraph objects do not match ({strict=})"
            )

    if how == "per_chain":
        it_left_chain = left.iter_chains(skip_if_no_output=True)
        it_right_chain = right.iter_chains(skip_if_no_input=True)
        chain_pairs = zip([*it_left_chain], [*it_right_chain], strict=strict)
        links = [
            ((il, *l[1:]), (ir, *r[1:]))  # output -> input
            for (il, lchain), (ir, rchain) in chain_pairs
            for (l, r) in create_links(
                lchain.iter_output_pads(**iter_kws), rchain.iter_input_pads(**iter_kws)
            )
        ]
    else:
        links = create_links(
            left.iter_output_pads(**iter_kws), right.iter_input_pads(**iter_kws)
        )

    fg = left._connect(
        right,
        links,
        chain_siso,
        replace_sws_flags,
    )
    if fg == NotImplemented:
        fg = right._rconnect(
            left,
            links,
            chain_siso,
            replace_sws_flags,
        )
    return fg


def attach(
    left: fgb.abc.FilterGraphObject | str | list[fgb.abc.FilterGraphObject | str],
    right: fgb.abc.FilterGraphObject | str | list[fgb.abc.FilterGraphObject | str],
    left_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
    right_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
) -> fgb.Graph:
    """attach filter(s), chain(s), or label(s) to a filtergraph object

    :param left: input filtergraph object, filtergraph expression, or label, or list thereof
    :param right: output filterchain, filtergraph expression, or label, or list thereof.
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
        if isinstance(obj, str):
            attach_obj = True
            obj = [obj]

        return obj, attach_obj

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
            "Cannot determine which side is attaching. One of left or right argument must be a Filter or Chain object."
        )

    nlinks = len(left_objs_labels) if attach_left else len(right_objs_labels)

    # put single index arguments as lists of indices
    if left_on is None:
        left_on = [None] * nlinks
    elif not isinstance(left_on, list):
        left_on = [left_on]
    if right_on is None:
        right_on = [None] * nlinks
    elif not isinstance(right_on, list):
        right_on = [right_on]

    def resolve_indices(base, branches, base_indices, branch_indices, base_is_input):
        # resolve all the specified pad indices of the base object
        base_indices = [
            (
                idx
                if idx is None
                else base._resolve_pad_index(idx, is_input=base_is_input)
            )
            for idx in base_indices
        ]

        # assign unspecified left pads
        base_def = [idx for idx in base_indices if idx is not None]
        iter_base_pads = (
            base.iter_input_pads if base_is_input else base.iter_output_pads
        )
        it_base_pad = (
            idx for idx in iter_base_pads(full_pad_index=True) if idx not in base_def
        )
        base_indices = [
            next(it_base_pad)[0] if idx is None else idx for idx in base_indices
        ]

        # resolve the specified attaching pad indices
        get_branch_pad = "next_output_pad" if base_is_input else "next_input_pad"
        branch_indices = [
            (
                idx
                if isinstance(robj, str)
                else (
                    getattr(robj, get_branch_pad)(full_pad_index=True)
                    if idx is None
                    else robj._resolve_pad_index(idx, is_input=not base_is_input)
                )
            )
            for robj, idx in zip(branches, branch_indices, strict=True)
        ]

        return base_indices, branch_indices

    if attach_right:
        left_on, right_on = resolve_indices(
            left_objs_labels, right_objs_labels, left_on, right_on, False
        )
    else:
        right_on, left_on = resolve_indices(
            right_objs_labels, left_objs_labels, right_on, left_on, True
        )

    if attach_right:
        return left_objs_labels._attach(right_objs_labels, left_on, right_on)
    else:
        return right_objs_labels._rattach(left_objs_labels, left_on, right_on)


def concatenate(*fgs):
    # TODO
    raise NotImplementedError()


def stack(
    *fgs: fgb.abc.FilterGraphObject,
    auto_link: bool = False,
    use_last_sws_flags: bool | None = None,
) -> fgb.Graph:
    """stack filtergraph objects

    :param fgs: filtergraph objects
    :param auto_link: True to connect matched I/O labels, defaults to None
    :param use_last_sws_flags: True to use ``sws_flags`` of the last object with one,
                               False to use ``sws_flags`` of the first object with one ``,
                               None to throw an exception if multiple ``sws_flags`` encountered (default)
    :return: new filtergraph object

    Remarks
    -------
    - extend() and import links
    - If `auto-link=False`, common labels may be renamed.
    - For more explicit linking rather than the auto-linking, use `connect()` instead.

    TO-CHECK/TO-DO: what happens if common link labels are already linked
    """

    if len(fgs) == 0:
        return fgb.Graph()

    fg = fgb.as_filtergraph(True)

    replace_sws_flags = None
    for other in fgs[1:]:
        if use_last_sws_flags is not None:
            replace_sws_flags = True if fg.sws_flags is None else use_last_sws_flags
        fg = fg._stack(fgb.as_filtergraph_object(other), auto_link, replace_sws_flags)

    return fg
