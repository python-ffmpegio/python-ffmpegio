from __future__ import annotations

from .. import filtergraph as fgb
from .typing import JOIN_HOW, PAD_INDEX, Literal

__all__ = ["connect", "join", "stack"]


def stack(
    *fgs: fgb.abc.FilterGraphObject,
    auto_link: bool = False,
    sws_flags_policy: Literal["first", "last"] | int | None = None,
) -> fgb.Graph:
    """stack filtergraph objects

    :param fgs: filtergraph objects
    :param auto_link: :code:`True` to connect matched I/O labels, defaults to :code:`None` 
    :param sws_flags_policy: Defines how to set :code:`sws_flags`:

        * :code:`'first'`: to use the first :code:`sws_flags` found among the
            filtergraphs (searched :code:`self` first then :code:`others`)
        * :code:`'last'`: use this filtergraph's :code:`sws_flags` (or none used if
            not set).
        * :code:`int`: specify which filtergraph's :code:`sws_flags` to use. :code:`0`
            refers to this object, :code:`1` refers to :code:`others[0]`, etc.
        * :code:`None`: if more than one have the :code:`sws_flags` set, raises
            :code:`FFmpegioError` exception. Otherwise, it uses the only one found
            or none if none not found.

    :return: a new filtergraph object

    Remarks
    -------

    - If `auto-link=False`, duplicate labels may be renamed with unique trailing
      digits.
    - For more explicit linking rather than the auto-linking, use `connect()` instead.

    """

    return fgb.as_filtergraph_object(fgs[0]).stack(
        *fgs[1:], auto_link=auto_link, sws_flags_policy=sws_flags_policy
    )


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
    :param from_left: output pad ids or labels of :code:`left` fg
    :type from_left: PAD_INDEX | str | list[PAD_INDEX | str]
    :param to_right: input pad ids or labels of the :code:`right` fg
    :type to_right: PAD_INDEX | str | list[PAD_INDEX | str]
    :param from_right: output pad ids or labels of the `ri`ght` fg, defaults to :code:`None` 
    :type from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None
    :param to_left: input pad ids or labels of this :code:`left` fg, defaults to :code:`None` 
    :type to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None
    :param chain_siso: True to chain the single-input single-output connection, default: True
    :param sws_flags_policy: Defines how to set :code:`sws_flags`:

        * :code:`'first'`: to use the first :code:`sws_flags` found among the
            filtergraphs (searched :code:`self` first then :code:`others`)
        * :code:`'last'`: use this filtergraph's :code:`sws_flags` (or none used if
            not set).
        * :code:`int`: specify which filtergraph's :code:`sws_flags` to use. :code:`0`
            refers to this object, :code:`1` refers to :code:`others[0]`, etc.
        * :code:`None`: if more than one have the :code:`sws_flags` set, raises
            :code:`FFmpegioError` exception. Otherwise, it uses the only one found
            or none if none not found.

    :return: new filtergraph object

    Notes
    -----

    * link labels may be auto-renamed if there is a conflict

    """

    return fgb.as_filtergraph_object(left).connect(
        right,
        from_left,
        to_right,
        from_right=from_right,
        to_left=to_left,
        chain_siso=chain_siso,
        sws_flags_policy=sws_flags_policy,
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
    :param how: method on how to mate input and output, defaults to :code:`"per_chain"`.

        - :code:`'chainable'`: joins only chainable input pads and output pads.
        - :code:`'per_chain'`: joins one pair of first available input pad and output pad of each
                            mating chains. Source and sink chains are ignored.
        - :code:`'all'`: joins all input pads and output pads
        - :code:`'auto'`: tries :code:`'per_chain'` first, if fails, then tries :code:`'all'`.

    :param n_links: number of left output pads to be connected to the right input pads, default: 0
                    (all matching links). If :code:`how=='per_chain'`, :code:`n_links` connections are made
                    per chain.
    :param strict: True to raise exception if numbers of available pads do not match, default: False
    :param unlabeled_only: True to ignore labeled unconnected pads, defaults to False
    :param chain_siso: True to chain the single-input single-output connection, default: True
    :param sws_flags_policy: Defines how to set :code:`sws_flags`:

        * :code:`'first'`: to use the first :code:`sws_flags` found among the
            filtergraphs (searched :code:`self` first then :code:`others`)
        * :code:`'last'`: use this filtergraph's :code:`sws_flags` (or none used if
            not set).
        * :code:`int`: specify which filtergraph's :code:`sws_flags` to use. :code:`0`
            refers to this object, :code:`1` refers to :code:`others[0]`, etc.
        * :code:`None`: if more than one have the :code:`sws_flags` set, raises
            :code:`FFmpegioError` exception. Otherwise, it uses the only one found
            or none if none not found.

    :return: Graph with the appended filter chains or None if inplace=True.
    """

    return fgb.as_filtergraph_object(left).join(
        right,
        how=how,
        n_links=n_links,
        strict=strict,
        unlabeled_only=unlabeled_only,
        chain_siso=chain_siso,
        sws_flags_policy=sws_flags_policy,
    )
