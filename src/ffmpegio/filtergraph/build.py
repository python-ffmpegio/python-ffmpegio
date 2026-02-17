from __future__ import annotations

from copy import copy

from .. import filtergraph as fgb
from .exceptions import FFmpegioError
from .typing import JOIN_HOW, PAD_INDEX, Literal, get_args

__all__ = ["connect", "join", "attach", "stack"]


def stack(
    *fgs: fgb.abc.FilterGraphObject,
    auto_link: bool = False,
    sws_flags_policy: Literal["first", "last"] | int | None = None,
) -> fgb.Graph:
    """stack filtergraph objects

    :param fgs: filtergraph objects
    :param auto_link: ``True`` to connect matched I/O labels, defaults to None
    :param sws_flags_policy: Defines how to set ``sws_flags``:

        * ``'first'``: to use the first ``sws_flags`` found among the
            filtergraphs (searched ``self`` first then ``others``)
        * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
            not set).
        * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
            refers to this object, ``1`` refers to ``others[0]``, etc.
        * ``None``: if more than one have the ``sws_flags`` set, raises
            ``FFmpegioError`` exception. Otherwise, it uses the only one found
            or none if none not found.

    :return: a new filtergraph object

    Remarks
    -------

    - If `auto-link=False`, duplicate labels may be renamed with unique trailing
      digits.
    - For more explicit linking rather than the auto-linking, use `connect()` instead.

    """

    return fgs[0].stack(*fgs[1:], auto_link, sws_flags_policy)


def connect(
    left: fgb.abc.FilterGraphObject | str,
    right: fgb.abc.FilterGraphObject | str,
    from_left: PAD_INDEX | str | list[PAD_INDEX | str],
    to_right: PAD_INDEX | str | list[PAD_INDEX | str],
    *,
    from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
    to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
    chain_siso: bool = True,
    sws_flags_policy: Literal["first", "last"] | int | None = None,
) -> fgb.Graph | fgb.Chain:
    """connect two filtergraph objects and make explicit connections

    :param left: transmitting filtergraph object
    :param right: receiving filtergraph object
    :param from_left: output pad ids or labels of ``left`` fg
    :param to_right: input pad ids or labels of the ``right`` fg
    :param from_right: output pad ids or labels of the `ri`ght` fg
    :param to_left: input pad ids or labels of this ``left`` fg
    :param chain_siso: True to chain the single-input single-output connection, default: True
    :param sws_flags_policy: Defines how to set ``sws_flags``:

        * ``'first'``: to use the first ``sws_flags`` found among the
            filtergraphs (searched ``self`` first then ``others``)
        * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
            not set).
        * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
            refers to this object, ``1`` refers to ``others[0]``, etc.
        * ``None``: if more than one have the ``sws_flags`` set, raises
            ``FFmpegioError`` exception. Otherwise, it uses the only one found
            or none if none not found.

    :return: new filtergraph object

    Notes
    -----

    * link labels may be auto-renamed if there is a conflict

    """

    return left.connect(
        right, from_left, to_right, from_right, to_left, chain_siso, sws_flags_policy
    )


def join(
    left: fgb.abc.FilterGraphObject | str,
    right: fgb.abc.FilterGraphObject | str,
    how: JOIN_HOW | None = None,
    n_links: int | Literal["all"] | None = None,
    strict: bool = False,
    unlabeled_only: bool = False,
    chain_siso: bool = True,
    sws_flags_policy: Literal["first", "last"] | int | None = None,
) -> fgb.Graph | fgb.Chain:
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
    :param sws_flags_policy: Defines how to set ``sws_flags``:

        * ``'first'``: to use the first ``sws_flags`` found among the
            filtergraphs (searched ``self`` first then ``others``)
        * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
            not set).
        * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
            refers to this object, ``1`` refers to ``others[0]``, etc.
        * ``None``: if more than one have the ``sws_flags`` set, raises
            ``FFmpegioError`` exception. Otherwise, it uses the only one found
            or none if none not found.

    :return: Graph with the appended filter chains or None if inplace=True.
    """

    # if one of the filtergraphs is empty, return the other (or a copy thereof)
    if not fgb.as_filtergraph_object(right).get_num_filters():
        if inplace:
            return left
        else:
            return fgb.as_filtergraph_object(left).copy()
    if not fgb.as_filtergraph_object(left).get_num_filters():
        if inplace:
            return right
        else:
            return copy(fgb.as_filtergraph_object(right))

    if how is None:
        how = "auto"
    if n_links is None:
        n_links = "all"

    if how not in get_args(JOIN_HOW):
        raise ValueError(f"{how=} is an unknown matching method")

    # make sure right is a Graph, Chain, or Filter object
    left = fgb.as_filtergraph_object(left, copy=not inplace)
    right = fgb.as_filtergraph_object(right, copy=not inplace)

    # handle joining empty graph
    nright = right.get_num_chains()
    if not nright:
        return left
    nleft = left.get_num_chains()
    if not nleft:
        return right

    iter_kws = {"unlabeled_only": unlabeled_only, "full_pad_index": True}
    if how == "chainable":
        iter_kws["chainable_only"] = True

    if n_links == "all" or n_links < 0:
        n_links = 0

    if how in ("per_chain", "auto") and nright == nleft:
        #
        try:
            links = [None] * nleft
            for c in range(nleft):
                # get the first available pad to join
                left_pad, *_ = next(left.iter_output_pads(chain=c, **iter_kws))
                right_pad, *_ = next(right.iter_input_pads(chain=c, **iter_kws))
                links[c] = (left_pad, right_pad)
        except:
            if how == "auto":
                how = "all"
            else:
                raise

    if how in ("all", "chainable") or nright != nleft:
        left_pads = [out[0] for out in left.iter_output_pads(**iter_kws)]
        right_pads = [out[0] for out in right.iter_input_pads(**iter_kws)]

        nleft, nright = len(left_pads), len(right_pads)
        if strict and nleft != nright:
            raise FFmpegioError("`[stict=True] number of unconnected pads must match.")
        n_max = min(nleft, nright)
        n_links = n_max if n_links <= 0 else min(n_links, n_max)

        links = [None] * n_links
        for i, (left_pad, right_pad) in enumerate(
            zip(left_pads[:n_links], right_pads[:n_links])
        ):
            links[i] = (left_pad, right_pad)

    fg = left._connect(
        right,
        links,
        [],
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
