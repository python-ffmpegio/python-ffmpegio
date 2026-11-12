from __future__ import annotations

import os
from collections import UserList
from collections.abc import Callable, Iterator, Iterable, Sequence
from contextlib import contextmanager
from itertools import accumulate, chain
from math import floor, log10
from tempfile import NamedTemporaryFile

from .._typing import Literal
from ..errors import FFmpegioError
from ..stream_spec import is_map_option
from . import abc
from . import utils as filter_utils
from .chains import Chain
from .convert import as_filterchain, as_filtergraph, as_filtergraph_object
from .exceptions import (
    FiltergraphInvalidExpression,
    FiltergraphInvalidIndex,
    FiltergraphPadNotFoundError,
)
from .filters import Filter
from .graph_links import GraphLinks
from .typing import PAD_INDEX

__all__ = ["Graph"]


def resolve_connect_pad_indices(
    left: abc.FilterGraphObject,
    right: abc.FilterGraphObject,
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
        incomplete pad index (those with `None`) will raise Filtergrap0hPadNotFoundError

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


class Graph(abc.FilterGraphObject, UserList):
    class Error(FFmpegioError):
        pass

    class FilterPadMediaTypeMismatch(Error):
        def __init__(self, in_name, in_pad, in_type, out_name, out_pad, out_type):
            super().__init__(
                f"mismatched pad types: {in_name}:{in_pad}[{in_type}] => {out_name}:{out_pad}[{out_type}]"
            )

    class InvalidFilterPadId(Error):
        def __init__(self, type, index):
            super().__init__(f"invalid {type} filter pad index: {index}")

    _unc_label: str = "UNC"

    def __init__(
        self,
        filter_specs: (
            str
            | abc.FilterGraphObject
            | Iterable[Chain | str | Iterable[Filter]]
            | None
        ) = None,
        links: (
            dict[
                str | int,
                tuple[
                    PAD_INDEX | Sequence[PAD_INDEX] | None,
                    PAD_INDEX | None,
                ],
            ]
            | GraphLinks
            | None
        ) = None,
        sws_flags: str | None = None,
    ):
        """FFmpeg filtergraph

        :param filter_specs: filtergraph specification, defaults to create an
            empty graph. Acceptable formats include:

            * :code:`str` FFmpeg filtergraph expression. Note: :code:`links` and
                :code:`sws_flags` arguments are ignored.
            * Another :code:`Graph` object to copy
            * A :code:`Chain` object as the first and only chain of the filtergraph
            * A :code:`Filter` object to place the filter on the first chain
            * An iterable of :code:`Chain` constructor arguments

        :param links: a dict specifying the inter-chain connections and input
            and output labels, defaults to none specified.

            Dict keys specify the link labels, each of which may be:

                * A :code:`str` with or without the bracket (e.g., :code:`'[in]'` or
                  :code:`'in'`). To specify connections to an input stream, the key
                  must be a valid map option, e.g. :code:`'0:v:0'` or :code:`'0:a:0'`.
                * An :code:`int` value which will be converted to :code:`'L0'`, :code:`'L1'`,
                  etc. when :code:`Graph` object is converted to :code:`str`.

            These labels may change during the lifespan of a :code:`Graph` object.
            As it is combining with another :code:`Graph` object duplicate labels
            may be assigned. Duplicates :code:`str` labels are resolved by trailing
            numbers. E.g., :code:`'in0'`, :code:`'in1'`, ... Duplicate :code:`int` labels
            are simply renumbered.

            Dict values are two-element tuples and must follow one of 4 formats:

                * Link label :code:`(to_pad, from_pad)`: connecting the output pad
                  :code:`from_pad` to the input pad :code:`to_pad`.
                * Input label :code:`(in_pad, None)`: Only defining the :code:`in_pad`
                * Output label :code:`(None, out_pad)`: Only defining the :code:`out_pad`
                * Input streams :code:`([in_pad0, in_pad1, ...], None)`: Multiple
                  input pads can be specified only for input stream connection.

        :param sws_flags: :code:`flags` option of automatically inserted :code:`scale`
            filters, defaults to use the FFmpeg default (:code:`='bicubic'`). FFmpeg
            automatically inserts :code:`scale` filters where format conversion is
            required.

        Examples
        ^^^^^^^^

        .. code:: python

            import ffmpegio.filtergraph as fgb

            # from FFmpeg filtergraph expression
            fg = fgb.Graph('[in]yadif=0:0:0[middle];[middle]scale=iw/2:-1[out]')

            # same graph but specify separate chains
            fg = fgb.Graph(['yadif=0:0:0', 'scale=iw/2:-1'],
                           links={'in':     ((0,0,0), None)),
                                  'middle': ((0,0,0), (1,0,0)),
                                  'out':    (None,    (1,0,0))})

        """
        if isinstance(filter_specs, str):
            # parse ffmpeg filtergraph expression
            filter_specs, links, sws_flags = filter_utils.parse_graph(
                filter_specs, False
            )
        elif filter_specs is None:
            # empty graph
            filter_specs = ()
        elif isinstance(filter_specs, Graph):
            # copy constructor, pull links and sws_flags aside
            links = filter_specs._links
            sws_flags = filter_specs.sws_flags and [*filter_specs.sws_flags]
        elif isinstance(filter_specs, Filter):
            filter_specs = [[filter_specs]]
        elif isinstance(filter_specs, Chain):
            filter_specs = [filter_specs] if len(filter_specs) else ()

        super().__init__((Chain(c) for c in filter_specs))

        self._links = GraphLinks(links)
        """utils.fglinks.GraphLinks: filtergraph link specifications
        """

        self.sws_flags = None if sws_flags is None else str(sws_flags)
        """Filter|None: swscale flags for automatically inserted scalers
        """

    @property
    def links(self) -> GraphLinks | None:
        """full filtergraph link definition"""
        return self._links

    def get_num_chains(self) -> int:
        """get the number of hains"""
        return len(self)

    def get_num_filters(self, chain: int | None = None) -> int:
        """get the number of filters of the specfied chain

        :param chain: id of the chain, defaults to :code:`None`  to get the total number
                      of filters across all chains
        """

        if chain is None:
            return sum(len(fc) for fc in self)

        if chain < 0 or chain >= len(self):
            raise ValueError(f"{chain=} is invalid.")
        return len(self[chain])

    def is_simple_chain(self) -> bool:
        """:code:`True` if the filtergraph is a simple chain"""

        return len(self) <= 1 and len(self.links) == 0 and self.sws_flags is None

    def resolve_pad_index(
        self,
        index_or_label: PAD_INDEX | str | None,
        *,
        is_input: bool = True,
        chain_id_omittable: bool = False,
        filter_id_omittable: bool = False,
        pad_id_omittable: bool = False,
        resolve_omitted: bool = True,
        chain_fill_value: int | None = None,
        filter_fill_value: int | None = None,
        pad_fill_value: int | None = None,
        chainable_first: bool = False,
    ) -> PAD_INDEX:

        # resolve a label string to pad index
        if isinstance(index_or_label, str):  # label given
            if self._links.is_linked(index_or_label, include_stream_specs=True):
                raise FiltergraphPadNotFoundError(
                    f"Pad with label='{index_or_label}' is already linked"
                )

            # input/output label (input streams excluded)
            try:
                inpad, outpad = self._links[index_or_label]
            except KeyError:
                raise FiltergraphPadNotFoundError(
                    f"Pad with label='{index_or_label}' does not exist"
                )

            return inpad if is_input else outpad

        # obtain 3-element tuple index (unvalidated)
        return super().resolve_pad_index(
            index_or_label,
            is_input=is_input,
            chain_id_omittable=chain_id_omittable,
            filter_id_omittable=filter_id_omittable,
            pad_id_omittable=pad_id_omittable,
            resolve_omitted=resolve_omitted,
            chain_fill_value=chain_fill_value,
            filter_fill_value=filter_fill_value,
            pad_fill_value=pad_fill_value,
            chainable_first=chainable_first,
        )

    def normalize_pad_index(
        self, input: bool, index: PAD_INDEX
    ) -> tuple[int, int, int]:

        if isinstance(index, int):
            index = (0, 0, index)
        elif len(index) == 1:
            index = (0, 0, *index)
        elif len(index) == 2:
            index = (0, *index)
        elif index[-3] < 0:
            index = (len(self) + index[-3], *index[-2:])

        return self[index[0]].normalize_pad_index(input, index)

    def get_input_pad(
        self, index_or_label: PAD_INDEX | str
    ) -> tuple[PAD_INDEX, str | None]:
        index = self.resolve_pad_index(index_or_label, is_input=True)
        if index is None:
            raise FiltergraphPadNotFoundError(
                f"{index_or_label=} is not a valid input pad"
            )
        label = (
            index_or_label
            if isinstance(index_or_label, str)
            else self.links.find_inpad_label(index)
        )
        if self.links.is_input_stream(label):
            raise FiltergraphPadNotFoundError(
                f"{index_or_label=} is connected to an input stream"
            )
        return index, self._get_label(True, index)

    def _get_label(self, input: bool, index: PAD_INDEX):
        index = self.normalize_pad_index(input, index)

        return getattr(
            self._links, "find_inpad_label" if input else "find_outpad_label"
        )(index)

    def compose(
        self,
        show_unconnected_inputs: bool = True,
        show_unconnected_outputs: bool = True,
    ):
        """compose filtergraph

        :param show_unconnected_inputs: display [UNC#] on all unconnected input pads, defaults to True
        :param show_unconnected_outputs: display [UNC#] on all unconnected output pads, defaults to True
        """

        fg = self

        # label unconnected pads
        label = self._unc_label
        unc_pads = {}
        i = j = -1
        if show_unconnected_inputs:
            for i, (index, _, _) in enumerate(
                self.iter_input_pads(unlabeled_only=True)
            ):
                unc_pads[f"{label}{i}"] = (index, None)
        if show_unconnected_outputs:
            for j, (index, _, _) in enumerate(
                self.iter_output_pads(unlabeled_only=True)
            ):
                unc_pads[f"{label}{i + j + 1}"] = (None, index)

        links = {**fg._links, **unc_pads} if i >= 0 or j >= 0 else fg._links

        return filter_utils.compose_graph(fg, links, fg.sws_flags)

    def __repr__(self):
        type_ = type(self)
        expr = self.compose()
        nchains = len(self.data)
        pos = [0] * nchains
        i = n = 0
        for j, fc in enumerate(self):
            for k, filter in enumerate(fc):
                fstr = str(filter)
                i += n
                i = expr[i:].find(fstr) + i
                n = len(fstr)
                pos[j] = i

        pos = [expr.rfind(";", 0, i) + 1 for i in pos]
        pos.append(len(expr))

        prefix = "      chain"
        nzeros = floor(log10(nchains)) + 1 if nchains else 0
        fmt = f"0{nzeros}"
        chain_list = [
            f"{prefix}[{j:{fmt}}]: {expr[i0:i1]}"
            for j, (i0, i1) in enumerate(zip(pos[:-1], pos[1:]))
        ]
        if self.sws_flags:
            chain_list = [
                f"{[' '] * (len(prefix) + 3 + nzeros)}{expr[: pos[0]]}",
                *chain_list,
            ]
        if len(chain_list) > 12:
            chain_list = [
                chain_list[:-4],
                f"{[' '] * (len(prefix) + 3 + nzeros)}{expr[: pos[0]]}",
                chain_list[-3:],
            ]
        chain_list = "\n".join(chain_list)

        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{str(self)}\"
    Number of chains: {len(self)}
{chain_list}      
    Available input pads ({self.get_num_inputs()}): {", ".join((str(id[0]) for id in self.iter_input_pads()))}
    Available output pads: ({self.get_num_outputs()}): {", ".join((str(id[0]) for id in self.iter_output_pads()))}
"""

    def __setitem__(self, key, value):
        UserList.__setitem__(self, key, as_filterchain(value, copy=True))
        # TODO purge invalid links

    def __getitem__(self, key):
        """get filterchains/filter

        :param key: filterchain or filter indices
        :type key: int, slice, tuple(int|slice,int|slice)
        :return: selected filterchain(s) or filter
        :rtype: Graph|Chain|Filter
        """
        try:
            return UserList.__getitem__(self, key)
        except (IndexError, StopIteration) as e:
            raise e
        except Exception:
            try:
                assert len(key) == 2 and all((isinstance(k, int) for k in key))
                return UserList.__getitem__(self, key[0])[key[1]]
            except:
                raise TypeError(
                    "Graph indies must be integers, slices, or 2-element tuple of int"
                )

    def append(self, item: Chain | str):
        fc = as_filterchain(item, copy=True)
        if not len(fc):
            raise ValueError("Empty filterchain cannot be appended to filtergraph.")
        self.data.append(fc)

    def extend(
        self,
        other: Sequence[Chain | str] | abc.FilterGraphObject,
        auto_link: bool = False,
        force_link: bool = False,
    ):
        other = as_filtergraph(other)
        if any(not len(c) for c in other):
            raise ValueError("Empty filterchain cannot be appended to filtergraph.")
        self._links.update(
            other._links.map_chains(len(self)), auto_link=auto_link, force=force_link
        )
        self.data.extend(other.data)

    def insert(self, i: int, item: Chain | str):
        fc = as_filterchain(item)
        if not len(fc):
            raise ValueError("Empty filterchain cannot be appended to filtergraph.")
        self.data.insert(i, fc)
        self._links.adjust_chains(i, 1)

    def __delitem__(self, i: int):
        if i < 0:
            i += len(self)

        # delete the chain
        UserList.__delitem__(self, i)

        # delete all links with the specified chain
        self._links.remove_chains([i])

    def iter_chains(self) -> Iterator[Chain]:
        """iterate over chains of the filtergraphobject

        :yields: chain object
        """

        for c in self:
            yield c

    def _iter_pads(
        self,
        iter_filter_pad: Callable,
        pad_links: dict[PAD_INDEX, PAD_INDEX | str],
        pad: int | None,
        filter: int | None,
        chain: Literal[0] | None,
        exclude_chainable: bool,
        chainable_first: bool,
        include_connected: bool,
        unlabeled_only: bool,
        chainable_only: bool,
    ) -> Iterator[tuple[PAD_INDEX, Filter, PAD_INDEX | str | None]]:
        """Iterate over input pads of the filters on the filterchain

        :param filters: list of filters to iterate
        :param iter_filter_pad: Filter class function to iterate on filter pads
        :param pad: pad id
        :param filter: filter index
        :param chain: chain index
        :param exclude_chainable: True to leave out the last pads
        :param chainable_first: True to yield the last pad first then the rest
        :param include_connected: True to include pads connected to input streams, defaults to False
        :yield: filter pad index, filter object, and True if no connection
        """

        if len(self) == 0:
            return

        if chain is None:
            # iterate over all filters
            chains = self.data
            ioff = 0
        else:
            try:
                chains = [self.data[chain]]
            except IndexError:
                raise FiltergraphInvalidIndex(f"Invalid {chain=} id.")
            ioff = chain

        for i, c in enumerate(chains):
            j = (len(c) + filter) if filter is not None and filter < 0 else filter

            for pidx, f, other_pidx in iter_filter_pad(
                c,
                pad,
                j,
                exclude_chainable=exclude_chainable,
                chainable_first=chainable_first,
                include_connected=include_connected,
                chainable_only=chainable_only,
            ):
                index = (i + ioff, *pidx)

                try:
                    assert other_pidx is None
                    # retrieve a connected output pad or a label if just labeled
                    other_pidx = pad_links[index]
                except (AssertionError, KeyError):
                    # fails if chained or no link defined
                    yield index, f, other_pidx
                    continue

                # exclude unlinked label-only pads, including input streams
                # return output label or output pad connected to
                is_str = isinstance(other_pidx, str)
                if (is_str and not unlabeled_only) or (
                    not is_str and include_connected
                ):
                    yield index, f, other_pidx

    def iter_input_pads(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: int | None = None,
        *,
        exclude_stream_specs: bool | None = True,
        only_stream_specs: bool = False,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
        full_pad_index: bool = False,
    ) -> Iterator[tuple[PAD_INDEX, Filter, PAD_INDEX | str | None]]:

        for index, f, other_pidx in self._iter_pads(
            Chain.iter_input_pads,
            self._links.input_dict(),
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
            unlabeled_only,
            chainable_only,
        ):
            # exclude a pad connected to an input stream (unless it can be interpreted as a link label)
            is_stream_spec = is_map_option(other_pidx, allow_missing_file_id=True)
            if (
                (only_stream_specs and not is_stream_spec)
                or (
                    exclude_stream_specs is None
                    and is_stream_spec
                    and ":" in other_pidx
                )
                or (exclude_stream_specs and is_stream_spec)
            ):
                continue

            yield index, f, other_pidx

    def iter_output_pads(
        self,
        pad=None,
        filter=None,
        chain=None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
        full_pad_index: bool = False,
    ) -> Iterator[tuple[PAD_INDEX, Filter, PAD_INDEX | str | None]]:

        for v in self._iter_pads(
            Chain.iter_output_pads,
            self._links.output_dict(),
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
            unlabeled_only,
            chainable_only,
        ):
            yield v

    def get_num_inputs(self, exclude_input_streams: bool | None = None) -> int:
        return len(
            list(
                self.iter_input_pads(
                    exclude_stream_specs=exclude_input_streams,
                )
            )
        )

    def get_num_outputs(self, chainable_only=False):
        return len(list(self.iter_output_pads(chainable_only=chainable_only)))

    def iter_input_labels(
        self, exclude_stream_specs: bool | None = False
    ) -> Iterator[tuple[str, PAD_INDEX]]:
        for label_index in self._links.iter_inputs(exclude_stream_specs):
            yield label_index

    def iter_output_labels(self) -> Iterator[tuple[str, PAD_INDEX]]:
        for label_index in self._links.iter_outputs():
            yield label_index

    def copy(self):
        return Graph(self)

    def are_linked(
        self,
        inpad: PAD_INDEX | None,
        outpad: PAD_INDEX | None,
        check_input_stream: bool | None = None,
    ) -> bool:
        """:code:`True` if given pads are linked

        :param inpad: input pad index, default to :code:`None` to check if
            :code:`outpad` is connected to any input pad.
        :type inpad: PAD_INDEX | None
        :param outpad: output pad index, defaults to :code:`None` to check if
            :code:`inpad` is connected to any output pad or an input stream.
        :type outpad: PAD_INDEX | None,
        :param check_input_stream: :code:`True` to check inpad is connected to an
            input stream, or the default (:code:`None`) behavior to return :code:`False`
            for an ambiguous label such as :code:`'a'` or :code:`'v'`, and :code:`True` for
            definitive label such as :code:`'0:v:0'`.

        :code:`ValueError` will be raised if both :code:`inpad` and :code:`outpad` :code:`None` or
        if :code:`include_input_stream!=False` and :code:`outpad` is :code:`None`.

        """

        try:
            return self._links.are_linked(inpad, outpad, check_input_stream)
        except ValueError:
            raise

    def unlink(
        self,
        label: str | None = None,
        inpad: PAD_INDEX | None = None,
        outpad: PAD_INDEX | None = None,
    ):
        """unlink specified links

        :param label: specify all the links with this label, defaults to :code:`None` 
        :param inpad: specify the link with this inpad pad, defaults to :code:`None` 
        :type inpad: PAD_INDEX | None
        :param outpad: specify all the links with this outpad pad, defaults to :code:`None` 
        :type outpad: PAD_INDEX | None
        """
        self._links.unlink(label, inpad, outpad)

    def link(
        self,
        inpad: PAD_INDEX,
        outpad: PAD_INDEX,
        label: str | None = None,
        preserve_label: Literal[False, "input", "output"] = False,
        force: bool = False,
    ) -> str | int:
        """set a filtergraph link

        :param inpad: input pad ids
        :type inpad: PAD_INDEX
        :param outpad: output pad index
        :type outpad: PAD_INDEX
        :param label: desired label name, defaults to :code:`None`  (=reuse inpad/outpad label or unnamed link)
        :param preserve_label: `False` to remove the labels of the input and output pads (default) or
                               `'input'` to prefer the input label or `'output'` to prefer the output
                               label.
        :param force: True to drop conflicting existing link, defaults to False
        :return: assigned label of the created link. Unnamed links gets a
                 unique integer value assigned to it.

        ..notes:

            - Unless `force=True`, inpad pad must not be already connected
            - User-supplied label name is a suggested name, and the function could
              modify the name to maintain integrity.
            - If inpad or outpad were previously named, their names will be dropped
              unless one matches the user-supplied label.
            - No guarantee on consistency of the link label (both named and unnamed)
              during the life of the object

        """

        if label is not None:
            GraphLinks.validate_label(label, is_link=False, no_stream_spec=True)
        if inpad is not None:
            inpad = self.resolve_pad_index(inpad, is_input=True)
            try:
                f = self.data[inpad[0]][inpad[1]]
                assert inpad[2] >= 0 and inpad[2] < f.get_num_inputs()
            except:
                raise Graph.InvalidFilterPadId("input", inpad)
        if outpad is not None:
            outpad = self.resolve_pad_index(outpad, is_input=False)
            try:
                f = self.data[outpad[0]][outpad[1]]
                assert outpad[2] >= 0 and outpad[2] < f.get_num_outputs()
            except:
                raise Graph.InvalidFilterPadId("output", outpad)

        return self._links.link(inpad, outpad, label, preserve_label, force)

    def has_label(
        self, label: str, only_if: Literal["input", "output", "internal"] | None = None
    ) -> bool:
        """:code:`True` if a linklabel is defined

        :param label: name of the link label
        :param only_if: also check for the type of the label
        :return: True if exists
        """
        try:
            link = self._links[label]
        except KeyError:
            return False

        return (
            True
            if only_if is None
            else (
                (only_if == "input" and link[1] is None)
                or (only_if == "output" and link[0] is None)
                or (
                    only_if == "internal"
                    and link[0] is not None
                    and link[1] is not None
                )
            )
        )

    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX | None = None,
        outpad: PAD_INDEX | None = None,
        force: bool = None,
    ) -> Graph:
        """label a filter pad

        :param label: name of the new label. Square brackets are optional.
        :param inpad: input filter pad index or a sequence of pads, defaults to :code:`None` 
        :type inpad: PAD_INDEX | None
        :param outpad: output filter pad index, defaults to :code:`None` 
        :type outpad: PAD_INDEX | None
        :param force: True to delete existing labels, defaults to :code:`None` 
        :return: actual label name

        Only one of inpad and outpad argument must be given.

        If given label already exists, no new label will be created.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        if label[0] == "[" and label[-1] == "]":
            label = label[1:-1]

        if inpad is not None:
            GraphLinks.validate_pad_idx_pair((inpad, None))
            for d in GraphLinks.iter_inpad_ids(inpad):
                try:
                    f = self.data[d[0]][d[1]]
                    n = f.get_num_inputs()
                    assert d[2] >= 0 and d[2] < (n - 1 if d[1] > 0 else n)
                except:
                    raise Graph.InvalidFilterPadId("input", d)
        elif outpad is not None:
            GraphLinks.validate_pad_idx(outpad)
            try:
                f = self.data[outpad[0]][outpad[1]]
                assert outpad[2] >= 0 and outpad[2] < f.get_num_outputs()
            except:
                raise Graph.InvalidFilterPadId("output", outpad)
        else:
            raise Graph.Error("filter pad index is not given")

        self._links.create_label(label, inpad, outpad, force)

        return self

    def remove_label(self, label: str, inpad: PAD_INDEX | None = None):

        self._links.remove_label(label, inpad)

    def rename_label(self, old_label: str, new_label: str) -> str | None:
        """rename an existing link label

        :param old_label: existing label named
        :param new_label: new desired label name or None to make it unnamed label
        :return: actual label name or None if unnamed

        Note:

        - `new_label` is not guaranteed, and actual label depends on existing labels

        """

        if not (isinstance(old_label, str) and old_label):
            raise Graph.Error(f"old_label [{old_label}] must be a string.")

        if new_label is not None and not (isinstance(new_label, str) and new_label):
            raise Graph.Error(f"new_label [{new_label}] must be None or a string.")

        # return the actual label or None if unnamed
        return new_label or self._links.rename(old_label, new_label)

    def is_chain_siso(
        self,
        chain_id: int,
        check_input: bool = True,
        check_output: bool = True,
        check_link: bool = False,
    ) -> bool:
        """:code:`True` if specified filter chain is single-input and single-output

        :param chain_id: chain id
        :param check_input: False to check only for single-output, defaults to True
        :param check_output: False to check only for single-input, defaults to True
        :param check_link: True to return True if and only if the chain has no active connection, defaults to True
        """

        try:
            chain = self[chain_id]
        except IndexError:
            raise ValueError(f"{chain_id=} is an invalid chain id.")

        if len(chain) == 0:
            return False  # empty chain

        if check_input and chain[0].get_num_inputs() != 1:
            return False

        if check_output and chain[-1].get_num_outputs() != 1:
            return False

        return not (check_link and self._links.chain_has_link(chain_id))

    def is_chain_prependable(self, chain_id: int) -> bool:
        """:code:`True` if another chain can be prepended to the specified filter chain"""

        try:
            chain = self[chain_id]
        except IndexError:
            raise ValueError(f"{chain_id=} is an invalid chain id.")

        if len(chain) == 0:
            return True  # empty chain

        # must have at least one input pad
        nin = chain[0].get_num_inputs()
        if nin == 0:
            return False

        # make sure the chaining input pad is not already linked
        return not self._links.are_linked(inpad=(chain_id, 0, nin - 1))

    def is_chain_appendable(self, chain_id: int) -> bool:
        """:code:`True` if another chain can be appended to the specified filter chain

        :param chain_id: chain id
        """

        try:
            chain = self[chain_id]
        except IndexError:
            raise ValueError(f"{chain_id=} is an invalid chain id.")

        if len(chain) == 0:
            return True  # empty chain

        nout = chain[-1].get_num_outputs()
        if nout == 0:  # a sink filter, no connectivity
            return False

        # the last output pad must not be already connected
        filter_id = len(chain) - 1
        return not self._links.are_linked(outpad=(chain_id, filter_id, nout - 1))

    def stack(
        self,
        *others: tuple[abc.FilterGraphObject | str],
        auto_link: bool = False,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> tuple[Graph, list[int], list[dict[tuple[int, str | int], str | int]]]:

        if len(others) == 0:
            return self.copy() if not inplace else None

        others = list(as_filtergraph_object(obj) for obj in others)

        new_links, sws_flags, *_ = self._stack_analyze(
            others, auto_link, sws_flags_policy
        )

        return self._stack_create(others, inplace, new_links, sws_flags)

    def _stack_analyze(
        self,
        others: tuple[abc.FilterGraphObject],
        auto_link: bool,
        sws_flags_policy: Literal["first", "last"] | int | None,
        insert_at: int = 0,
    ) -> tuple[
        GraphLinks,
        str | None,
        list[int],
        list[dict[tuple[int, str | int], str | int]],
    ]:
        """first helper for filtergraph stacking

        :param others: list of the rest of the graphs to stack
        :param auto_link: True to auto-link the pad pairs with matching labels
        :param sws_flags_policy: inherits which filtergraph's sws_flags
        :param insert_at: where to insert self to others, defaults to 0 (as the first graph)
        :return new_links: mapping of the links from all the graphs
        :return sws_flags: inherited sws_flags
        :return chain_offsets: offset of chain index from the old to new
        :return link_mappings: mapping of old graphlink specs to new
        """

        fgs = list(others)
        fgs.insert(insert_at, self)

        old_links = [fg.links for fg in fgs]
        chain_offsets = [0, *accumulate(fg.get_num_chains() for fg in fgs[:-1])]
        new_links, link_mappings = GraphLinks.combine(old_links, chain_offsets)

        # if requested, link input and output pads with a matching label
        if auto_link:
            pairs = GraphLinks.pair_unconnected_labels(old_links)
            for label, in_fg, out_fg in pairs:
                in_label = link_mappings[in_fg][label]
                out_label = link_mappings[out_fg][label]
                new_links.link_by_labels(in_label, out_label, label=label)

        # pick sws_flags
        if isinstance(sws_flags_policy, int):
            fg = fgs[sws_flags_policy]
            sws_flags = fg.sws_flags if isinstance(fg, Graph) else None
        else:
            iter_sws_flags = (
                fg.sws_flags
                for fg in (fgs if sws_flags_policy != "last" else fgs[::-1])
                if isinstance(fg, Graph) and fg.sws_flags is not None
            )
            sws_flags = next(iter_sws_flags, None)

            if sws_flags_policy is None and next(iter_sws_flags, None) is not None:
                raise Graph.Error(
                    f"{sws_flags_policy=} and more than 1 filtergraphs has sws_flags"
                )

        return new_links, sws_flags, chain_offsets, link_mappings

    def _stack_create(
        self,
        others: Sequence[abc.FilterGraphObject],
        inplace: bool,
        new_links: GraphLinks,
        sws_flags: Sequence[str] | None,
        insert_at: int = 0,
    ) -> Graph:
        if inplace:
            # extend self.data and replace its links and sws_flags
            self.data = [
                *(
                    Chain(fc)
                    for fc in chain(*(fg.iter_chains() for fg in others[:insert_at]))
                ),
                *self.data,
                *(
                    Chain(fc)
                    for fc in chain(*(fg.iter_chains() for fg in others[insert_at:]))
                ),
            ]
            self._links = new_links
            self.sws_flags = sws_flags
            return self
        else:
            return Graph(
                chain(
                    *(
                        fg.iter_chains()
                        for fg in chain(others[:insert_at], self, others[insert_at:])
                    )
                ),
                new_links,
                sws_flags,
            )

    def connect(
        self,
        right: abc.FilterGraphObject,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        *,
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> Graph:

        return self._connect(
            right,
            from_left,
            to_right,
            from_right,
            to_left,
            chain_siso,
            sws_flags_policy,
            inplace,
            self.get_num_chains(),
        )

    def rconnect(
        self,
        left: abc.FilterGraphObject,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        *,
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
    ) -> Graph:

        return self._connect(
            left,
            from_right or [],
            to_left or [],
            from_left,
            to_right,
            chain_siso,
            sws_flags_policy,
            False,
            0,
        )

    def _connect(
        self,
        other: abc.FilterGraphObject,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None,
        chain_siso: bool,
        sws_flags_policy: Literal["first", "last"] | int | None,
        inplace: bool,
        insert_at: int,  # 0:connect, 1:rconnect
    ) -> Graph:
        """helper function for self.connect() & self.rconnect()"""

        # for ease of reading code
        left, right = (self, as_filtergraph_object(other))

        if not isinstance(from_left, list):
            from_left = [from_left]
        if not isinstance(to_right, list):
            to_right = [to_right]
        if len(from_left) != len(to_right):
            raise ValueError("Mismatched number of pads in 'from_right' and 'to_left'")

        if from_right is None:
            from_right = []
        elif not isinstance(from_right, list):
            from_right = [from_right]
        if to_left is None:
            to_left = []
        elif not isinstance(to_left, list):
            to_left = [to_left]
        if len(from_right) != len(to_left):
            raise ValueError("Mismatched number of pads in 'from_left' and 'to_right'")

        nb_left_chains = len(left)
        assert insert_at in {0, nb_left_chains}, (
            "Only insertion at beginning or end of the graph is currently supported."
        )

        left_at = 0 if insert_at else 1
        new_links, sws_flags, chain_offsets, link_mappings = left._stack_analyze(
            [right], False, sws_flags_policy, left_at
        )

        # convert the connecting pads to the new stacked graph to be created

        def get_pads(
            fg: abc.FilterGraphObject, pad: PAD_INDEX | str, is_input: bool
        ) -> tuple[int, int, int] | str:
            is_second = (fg == right) ^ (insert_at == 0)
            if isinstance(pad, str):
                pad = new_links[link_mappings[is_second][pad]][not is_input]
            else:
                pad = fg.normalize_pad_index(is_input, pad)
                pad = (pad[0] + chain_offsets[is_second], *pad[1:])
            return pad

        out_pads = [
            get_pads(fg, pad, False)
            for fg, pads in [(left, from_left), (right, from_right or [])]
            for pad in pads
        ]

        in_pads = [
            get_pads(fg, pad, True)
            for fg, pads in [(right, to_right), (left, to_left or [])]
            for pad in pads
        ]

        # create new graph (note: new_fg==self if inplace=True)
        new_fg = left._stack_create([right], inplace, new_links, sws_flags, left_at)
        n_inserted = len(new_fg) - nb_left_chains
        new_links = new_fg._links

        # pair the links (separate links to be chained instead)

        stack_links = []
        chain_links = []

        for out_pad, in_pad in zip(out_pads, in_pads):  # self -> right
            if (
                chain_siso
                and new_fg._output_pad_is_chainable(out_pad)
                and new_fg._input_pad_is_chainable(in_pad)
            ):
                chain_links.append((out_pad, in_pad))
            else:
                stack_links.append((out_pad, in_pad))

        # connect non-chaining links
        for out_pad, in_pad in stack_links:
            new_links.link(in_pad, out_pad)

        # combine chains if any chain_links specified
        if len(chain_links):
            # sort chain_pairs in descending order of trailing chain
            chain_pairs = sorted(
                ((out_pad, in_pad) for out_pad, in_pad in chain_links),
                key=lambda cp: min(cp[0], cp[1]),
                reverse=True,
            )

            # joining chains
            insert_end = insert_at + n_inserted
            for out_pad, in_pad in chain_pairs:
                cid_out, cid_in = out_pad[0], in_pad[0]

                if cid_out < insert_at or cid_out >= insert_end:
                    # input chain (out_pad) is the host chain: append in_pad chain to out_pad chain

                    # fix the existing links
                    new_links.combine_chains(
                        out_pad, in_pad, len(new_fg[cid_out]), prepend=False
                    )

                    # move the trailing chain to the end of the leading chain
                    fc = new_fg.pop(cid_in)
                    new_fg[cid_out - (cid_in < cid_out)].extend(fc)
                else:
                    # output chain (in_pad) is the host chain: prepend out_pad chain to in_pad chain

                    # fix the existing links
                    new_links.combine_chains(
                        out_pad, in_pad, len(new_fg[cid_out]), prepend=True
                    )

                    # move the trailing chain to the end of the leading chain
                    fc = new_fg.pop(cid_out)
                    cid = cid_in - (cid_out < cid_in)
                    new_fg[cid] = Chain([*fc, *new_fg[cid]])

        return new_fg

    def attach(
        self,
        right: abc.FilterGraphObject | str | list[str | tuple[PAD_INDEX, str]],
        left_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        right_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        *,
        chainable_only: bool | Literal["left", "right", "auto"] = "auto",
        chain_siso: bool = True,
        inplace: bool = False,
    ) -> Chain | Graph:

        if chainable_only == "auto":
            chainable_only = False

        try:
            right_is_label = False
            right_obj = as_filtergraph_object(right)
        except FiltergraphInvalidExpression:
            right_is_label = True

        # get output pads
        left_pads = (
            list(
                c[0]
                for c in self.iter_output_pads(
                    chainable_only=not right_is_label
                    and (chainable_only is True or chainable_only == "left"),
                    unlabeled_only=True,
                    full_pad_index=True,
                )
            )
            if left_on is None
            else [
                self.get_output_pad(
                    pad
                    if isinstance(pad, str)
                    else self.normalize_pad_index(False, pad)
                )[0]
                for pad in (left_on if isinstance(left_on, list) else [left_on])
            ]
        )

        # resolve the label attachment first
        if right_is_label:
            left = self if inplace else Graph(self)

            if not isinstance(right, list):
                right = [right]

            spec_pads = set()

            def scan_labels(label):
                if isinstance(label, tuple):
                    label = (
                        self.resolve_pad_index(
                            label[0],
                            is_input=False,
                            chain_id_omittable=True,
                            filter_id_omittable=True,
                        ),
                        label[1],
                    )
                    spec_pads.add(label[0])
                return label

            right = [scan_labels(label) for label in right]

            it_pad = iter(left_pads)
            for label in right:
                if isinstance(label, tuple):
                    # specifies output pad to attach to: fg >> (1, '[out]')
                    pad, label = label
                else:
                    for pad in it_pad:
                        if pad not in spec_pads:
                            break
                    else:
                        raise FiltergraphPadNotFoundError(
                            "Not enough available output pads found to attach the labels."
                        )
                left.add_label(label, outpad=pad)

            return None if inplace else left

        # get pads to be connected
        right_pads = (
            list(
                c[0]
                for c in right_obj.iter_input_pads(
                    chainable_only=chainable_only is True or chainable_only == "right",
                    full_pad_index=True,
                )
            )
            if right_on is None
            else [
                right_obj.get_input_pad(
                    pad if isinstance(pad, str) else self.normalize_pad_index(True, pad)
                )[0]
                for pad in (right_on if isinstance(right_on, list) else [right_on])
            ]
        )

        nconn = min(len(left_pads), len(right_pads))
        return self.connect(
            right_obj,
            left_pads[:nconn],
            right_pads[:nconn],
            inplace=inplace,
            chain_siso=chain_siso,
            sws_flags_policy="first",
        )

    def rattach(
        self,
        left: abc.FilterGraphObject | str | list[str | tuple[str, PAD_INDEX]],
        left_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        right_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        *,
        chainable_only: bool | Literal["left", "right", "auto"] = "auto",
        chain_siso: bool = True,
    ) -> Chain | Graph:

        if chainable_only == "auto":
            chainable_only = False

        try:
            left_is_label = False
            left_obj = as_filtergraph(left)
        except FiltergraphInvalidExpression:
            left_is_label = True

        # get input pads
        right_pads = (
            list(
                c[0]
                for c in self.iter_input_pads(
                    chainable_only=not left_is_label
                    and (chainable_only is True or chainable_only == "right"),
                    unlabeled_only=True,
                    full_pad_index=True,
                )
            )
            if right_on is None
            else [
                self.get_input_pad(
                    pad if isinstance(pad, str) else self.normalize_pad_index(True, pad)
                )[0]
                for pad in (right_on if isinstance(right_on, list) else [right_on])
            ]
        )

        # resolve the label attachment first
        if left_is_label:
            right = Graph(self)

            if not isinstance(left, list):
                left = [left]

            spec_pads = set()

            def scan_labels(label):
                if isinstance(label, tuple):
                    label = (
                        label[0],
                        self.resolve_pad_index(
                            label[1],
                            is_input=True,
                            chain_id_omittable=True,
                            filter_id_omittable=True,
                        ),
                    )
                    spec_pads.add(label[1])
                return label

            left = [scan_labels(label) for label in left]

            it_pad = iter(right_pads)
            for label in left:
                if isinstance(label, tuple):
                    # specifies output pad to attach to: fg >> (1, '[out]')
                    label, pad = label
                else:
                    for pad in it_pad:
                        if pad not in spec_pads:
                            break
                    else:
                        raise FiltergraphPadNotFoundError(
                            "Not enough available output pads found to attach the labels."
                        )
                right.add_label(label, inpad=pad)

            return right

        # get pads to be connected
        left_pads = (
            list(
                c[0]
                for c in left_obj.iter_output_pads(
                    chainable_only=chainable_only is True or chainable_only == "left",
                    full_pad_index=True,
                )
            )
            if left_on is None
            else [
                left_obj.get_output_pad(
                    pad
                    if isinstance(pad, str)
                    else left_obj.normalize_pad_index(False, pad)
                )[0]
                for pad in (left_on if isinstance(left_on, list) else [left_on])
            ]
        )

        nconn = min(len(left_pads), len(right_pads))

        return self.rconnect(
            left_obj,
            left_pads[:nconn],
            right_pads[:nconn],
            chain_siso=chain_siso,
            sws_flags_policy="first",
        )

    @contextmanager
    def as_script_file(self)->Iterator[str]:
        """return script file containing the filtergraph description

        :yields: path of a temporary text file with filtergraph description

        This method is intended to work with the `/filter` and `/filter_complex`
        FFmpeg options (for FFmpeg 6 or earlier, `filter_script` and
        `filter_complex_script`). FFmpeg options, by creating a temporary text file
        containing the filtergraph description.

        .. note::
          Only use this function when the filtergraph description is too long for
          OS to handle it. Presenting the filtergraph with a `filter_complex` or
          `filter` option to FFmpeg is always a faster solution.

          Moreover, if `stdin` is available, i.e., not for a write or filter
          operation, it is more performant to pass the long filtergraph object
          to the subprocess' `input` argument instead of using this method.

        Use this method with a `with` statement. How to incorporate its output
        with `ffmpegprocess` depends on the `as_file_obj` argument.

        :Example:

          The following example illustrates a usecase for a video SISO filtergraph:

          .. code-block:: python

             # assume `fg` is a SISO video filter Graph object

             with fg.as_script_file() as script_path:
                 ffmpegio.ffmpegprocess.run(
                     {
                         'inputs':  [('input.mp4', None)]
                         'outputs': [('output.mp4', {'filter_script:v': script_path})]
                     })

          As noted above, a performant alternative is to use an input pipe and
          feed the filtergraph description directly:

          .. code-block:: python

             ffmpegio.ffmpegprocess.run(
                 {
                     'inputs':  [('input.mp4', None)]
                     'outputs': [('output.mp4', {'filter_script:v': 'pipe:0'})]
                 },
                 input=str(fg))

          Note that :code:`pipe:0` must be used and not the shorthand :code:`'-'` unlike
          the input url.

        """

        # populate the file with filtergraph expression
        temp_file = NamedTemporaryFile("wt", delete=False)
        temp_file.write(str(self))
        temp_file.close()

        try:
            # present the file to the caller in the context
            yield temp_file.name

        finally:
            if temp_file:
                os.remove(temp_file.name)

    def _input_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """returns True if specified input pad index is available"""

        # check linked indices
        if self._links.are_linked(inpad=index, outpad=None, check_input_stream=True):
            # already connected
            return False

        # check the chain
        return self[index[0]]._input_pad_is_available((0, *index[1:]))

    def _output_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """returns True if specified output pad index is available"""

        # check linked indices
        if self._links.are_linked(outpad=index, inpad=None):
            # already connected
            return False

        return self[index[0]]._output_pad_is_available((0, *index[1:]))

    def _check_partial_pad_index(
        self, index: tuple[int | None, int | None, int | None], is_input: bool
    ) -> bool:
        """:code:`True` if defined values of the partial pad index are valid"""

        chain = index[0]
        if chain is not None and (chain < 0 or chain >= len(self)):
            return False

        return any(
            c._check_partial_pad_index((None, *index[1:]), is_input) for c in self
        )

    def _input_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """:code:`True` if specified input pad is chainable"""

        if self.are_linked(index, None, True):
            return False

        i = index[0]
        try:
            chain = self[i]
        except IndexError:
            # invalid chain index
            return False
        else:
            return chain._input_pad_is_chainable((0, *index[1:]))

    def _output_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """:code:`True` if specified output pad is chainable"""

        if self.are_linked(None, index):
            return False

        i = index[0]
        try:
            chain = self[i]
        except IndexError:
            # invalid chain index
            return False
        else:
            return chain._output_pad_is_chainable((0, *index[1:]))

    def __ior__(self, other):
        if len(other):
            fg = self | other if len(self) else Graph(other)
            self.data = fg.data
            self._links = fg._links
        return self

    def __iadd__(self, other):
        if len(other):
            fg = self + other if len(self) else Graph(other)
            self.data = fg.data
            self._links = fg._links
        return self

    def __irshift__(self, other):
        if len(other):
            fg = self >> other if len(self) else Graph(other)
            self.data = fg.data
            self._links = fg._links
        return self
