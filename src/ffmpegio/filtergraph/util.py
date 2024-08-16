from __future__ import annotations

from .typing import PAD_INDEX

from .. import filtergraph as fgb
from ..utils import zip # pre-py310 compatibility


def resolve_connect_pad_indices(
    left: fgb.abc.FilterGraphObject,
    right: fgb.abc.FilterGraphObject,
    from_left: list[PAD_INDEX | str | None],
    to_right: list[PAD_INDEX | str | None],
    from_right: list[PAD_INDEX | str | None],
    to_left: list[PAD_INDEX | str | None],
    resolve_omitted: bool,
) -> tuple[list[tuple[PAD_INDEX, PAD_INDEX]]]:
    """resolve and validate pad indices given for a filtergraph connect operation

    :param left: transmitting filtergraph object
    :param right: receiving filtergraph object
    :param from_left: output pad ids or labels of `left` fg (feedforward link sources)
    :param to_right: input pad ids or labels of the `right` fg (feedforward link destinations)
    :param from_right: output pad ids or labels of the `right` fg (feedback link sources)
    :param to_left: input pad ids or labels of this `left` fg (feedback destinations)
    :param resolve_omitted: True to resolve the `None`'s in the pad indices. If False, any 
                            incomplete pad index (those with `None`) will raise FiltergraphPadNotFoundError
    :return: tuple pairs of filter pad indices to be paired. Each tuple pair consists of two pad indices: the
             first is the source/output pad and the second is the destination/input pad.
    """

    # make sure the pads to be linked are all pairable
    try:
        fwd_links = [(l, r) for l, r in zip(from_left, to_right, strict=True)]
    except:
        raise ValueError(
            f"the number of pad indices in {from_left=} and {to_right=} must match."
        )

    try:
        bwd_links = [(l, r) for l, r in zip(from_right, to_left, strict=True)]
    except:
        raise ValueError(
            f"the number of pad indices in {from_right=} and {to_left=} must match."
        )

    # make sure all the link indices are 3-element tuples
    fwd_links = [
        (
            left.resolve_pad_index(l, is_input=False, resolve_omitted=resolve_omitted),
            right.resolve_pad_index(r, is_input=True, resolve_omitted=resolve_omitted),
        )
        for l, r in fwd_links
    ]
    bwd_links = [
        (
            right.resolve_pad_index(r, is_input=False, resolve_omitted=resolve_omitted),
            left.resolve_pad_index(l, is_input=True, resolve_omitted=resolve_omitted),
        )
        for r, l in bwd_links
    ]

    return fwd_links, bwd_links
