from __future__ import annotations

from collections import UserList
from collections.abc import Generator, Callable
from contextlib import contextmanager
from functools import partial, reduce
from copy import deepcopy
from math import floor, log10
import os
from tempfile import NamedTemporaryFile


from .typing import *
from .exceptions import *
from .abc import FilterOperations

from ..utils import filter as filter_utils, is_stream_spec
from .GraphLinks import GraphLinks

__all__ = ["Graph"]


class Graph(UserList, FilterOperations):
    """List of FFmpeg filterchains in parallel with interchain link specifications

    Graph() to instantiate empty Graph object

    Graph(obj) to copy-instantiate Graph object from another

    Graph('...') to parse an FFmpeg filtergraph expression

    Graph(filter_specs, links, sws_flags)
    to specify the compose_graph(...) arguments

    :param filter_specs: either an existing Graph instance to copy, an FFmpeg
                         filtergraph expression, or a nested sequence of argument
                         sequences to compose_filter() to define a filtergraph.
                         For the latter option, The last element of each filter argument
                         sequence may be a dict, defining its keyword arguments,
                         defaults to None
    :type filter_specs: Graph, str, or seq(seq(filter_args))
    :param links: specifies filter links
    :type links: dict, optional
    :param sws_flags: specify swscale flags for those automatically inserted
                      scalers, defaults to None
    :type sws_flags: seq of stringifyable elements with optional dict as the last
                     element for the keyword flags, optional

    """

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

    def __init__(
        self, filter_specs=None, links=None, sws_flags=None, autosplit_output=True
    ):

        # convert str to a list of filter_specs
        if isinstance(filter_specs, str):
            filter_specs, links, sws_flags = filter_utils.parse_graph(filter_specs)
        elif isinstance(filter_specs, Graph):
            links = filter_specs._links
            sws_flags = filter_specs.sws_flags and filter_specs.sws_flags[1:]
            autosplit_output = filter_specs.autosplit_output
        elif isinstance(filter_specs, Chain):
            filter_specs = [filter_specs] if len(filter_specs) else ()
        elif isinstance(filter_specs, Filter):
            filter_specs = [[filter_specs]]

        super().__init__(
            ()
            if filter_specs is None or not len(filter_specs)
            else (Chain(fspec) for fspec in filter_specs)
        )

        self._links = GraphLinks(links)
        """utils.fglinks.GraphLinks: filtergraph link specifications
        """

        self.sws_flags = None if sws_flags is None else Filter(["scale", *sws_flags])
        """Filter|None: swscale flags for automatically inserted scalers
        """

        self.autosplit_output = autosplit_output
        """bool: True to insert a split filter when an output pad is linked multiple times. default: True """

    def resolve_index(self, is_input: bool, index: PAD_INDEX | str) -> PAD_INDEX:
        """Resolve label or partial pad index to full 3-element pad index

        :param is_input: True if resolving a filter pad
        :param index: pad label or (partial) index
        :return: a full 3-element pad index
        """

        # call if index needs to be autocompleted
        try:
            if isinstance(index, str):
                # return the pad index associated with the label
                label = (
                    index[1:-1]
                    if len(index) > 2 and index[0] == "[" and index[-1] == "]"
                    else index
                )
                dsts, outpad = self._links[label]
                if is_input:  # outpad=None, inpad=not None
                    assert self._links.is_input(label)
                    return next(self._links.iter_inpad_ids(dsts))
                else:  # inpad=None, outpad=not None
                    assert self._links.is_output(label)
                    return outpad

            validate_pad_index(index)

            assert len(index) in (1, 2, 3)
            i = index[-1]
            try:
                j = index[-2]
            except:
                j = None
            try:
                k = index[-3]
            except:
                k = None

            # if any index is None, pick the first available
            if is_input:
                pad = next(self.iter_input_pads(chain=k, filter=j, pad=i))
            else:
                pad = next(
                    self.iter_output_pads(
                        chain=k, filter=j, pad=i, exclude_named=index is None
                    )
                )
            return pad[0]
        except:
            raise FiltergraphPadNotFoundError("input" if is_input else "output", index)

    def __str__(self) -> str:
        # insert split filters if autosplit_output is True
        fg = self.split_sources() if self.autosplit_output else self
        return filter_utils.compose_graph(
            fg, fg._links, fg.sws_flags and fg.sws_flags[1:]
        )

    def __repr__(self):
        type_ = type(self)
        expr = str(self)
        nchains = len(self.data)
        pos = [0] * nchains
        i = n = 0
        for j, chain in enumerate(self):
            for k, filter in enumerate(chain):
                fstr = str(filter)
                i += n
                i = expr[i:].find(fstr) + i
                n = len(fstr)
                pos[j] = i

        pos = [expr.rfind(";", 0, i) + 1 for i in pos]
        pos.append(len(expr))

        prefix = "      chain"
        nzeros = floor(log10(nchains)) + 1
        fmt = f"0{nzeros}"
        chain_list = [
            f"{prefix}[{j:{fmt}}]: {expr[i0:i1]}"
            for j, (i0, i1) in enumerate(zip(pos[:-1], pos[1:]))
        ]
        if self.sws_flags:
            chain_list = [f"{[' ']*(len(prefix)+3+nzeros)}{expr[:pos[0]]}", *chain_list]
        if len(chain_list) > 12:
            chain_list = [
                chain_list[:-4],
                f"{[' ']*(len(prefix)+3+nzeros)}{expr[:pos[0]]}",
                chain_list[-3:],
            ]
        chain_list = "\n".join(chain_list)

        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{str(self)}\"
    Number of chains: {len(self)}
{chain_list}      
    Available input pads ({self.get_num_inputs()}): {', '.join((str(id[0]) for id in self.iter_input_pads()))}
    Available output pads: ({self.get_num_outputs()}): {', '.join((str(id[0]) for id in self.iter_output_pads()))}
"""

    def __setitem__(self, key, value):
        super().__setitem__(key, as_filterchain(value, copy=True))
        # TODO purge invalid links

    def __getitem__(self, key):
        """get filterchains/filter

        :param key: filterchain or filter indices
        :type key: int, slice, tuple(int|slice,int|slice)
        :return: selected filterchain(s) or filter
        :rtype: Graph|Chain|Filter
        """
        try:
            return super().__getitem__(key)
        except (IndexError, StopIteration) as e:
            raise e
        except Exception as e:
            try:
                assert len(key) == 2 and all((isinstance(k, int) for k in key))
                return super().__getitem__(key[0])[1]
            except:
                raise TypeError(
                    "Graph indies must be integers, slices, or 2-element tuple of int"
                )

    def append(self, item):
        self.data.append(as_filterchain(item, copy=True))

    def extend(self, other, auto_link=False, force_link=False):
        other = as_filtergraph(other)
        self._links.update(
            other._links, len(self), auto_link=auto_link, force=force_link
        )
        self.data.extend(other)

    def insert(self, i, item):
        self.data.insert(i, as_filterchain(item))
        self._links.adjust_chains(i, 1)

    def __delitem__(self, i):
        # identify which indices are to be deleted

        indices = range(len(self.data))[i]
        if isinstance(indices, int):
            (k for k, v in self._links.items() if v[1] is not None and v[1][0] == i)
            self._links.iter_dsts()
            self._links.adjust_chains(i, -1)
        else:  # slice

            indices = sorted(indices)

            if i.step is not None and i.step == 1:
                # contiguous
                if i.start is not None:
                    pos = i.start
                    len = len(self.data) - n

        super().__delitem__(i)

    def __mul__(self, __n):
        # create a filtergraph with __n filterchains in parallel
        return (
            reduce(self.stack, [self] * (__n - 1), self)
            if isinstance(__n, int)
            else NotImplemented
        )

    def __rmul__(self, __n):
        # create a filtergraph with __n filterchains in parallel
        return (
            reduce(self.stack, [self] * (__n - 1), self)
            if isinstance(__n, int)
            else NotImplemented
        )

    def __add__(self, other):
        # join
        try:
            other = as_filtergraph_object(other)
        except Exception:
            return NotImplemented
        return self.join(other, "auto")

    def __radd__(self, other):
        # join
        try:
            other = as_filtergraph(other)
        except Exception:
            return NotImplemented
        return other.join(self, "auto")

    def __or__(self, other):
        # create filtergraph with self and other as parallel chains, self first

        try:
            other = as_filtergraph_object(other)
        except:
            return NotImplemented
        return self.stack(other)

    def __ror__(self, other):
        # create filtergraph with self and other as parallel chains, self last
        try:
            other = as_filtergraph(other)
        except:
            return NotImplemented
        return other.stack(self)

    def _chain(
        self, other: Filter | Chain, chain_index: int | None = None
    ) -> Chain | Graph:
        """chain self->other (no input check)

        If self is not a Graph, chain_index is ignored.
        If self is a Graph, chain_index may be used to specify the chain to attach other to.
        If not specified, attaches to the first chain.
        """
        return self.attach(other, (chain_index or 0, -1, -1), (0, 0, -1))

    def _rchain(
        self, other: Filter | Chain, chain_index: int | None = None
    ) -> Chain | Graph:
        """chain other->self (no input check)

        If self is not a Graph, chain_index is ignored.
        If self is a Graph, chain_index may be used to specify the chain to attach other to.
        If not specified, attaches to the first chain.
        """
        return self.rattach(other, (chain_index or 0, 0, -1), (0, -1, -1))

    def __iadd__(self, other):
        fg = self + other
        self.data = fg.data
        self._links = fg._links
        return self

    def __imul__(self, __n):
        fg = self * __n
        self.data = fg.data
        self._links = fg._links
        return self

    def __ior__(self, other):
        fg = self | other
        self.data = fg.data
        self._links = fg._links
        return self

    def __irshift__(self, other):
        fg = self >> other
        self.data = fg.data
        self._links = fg._links
        return self

    def _screen_input_pads(self, iter_pads, exclude_named, include_connected):

        links = self._links
        for index, f in iter_pads():  # for each input pad
            label = links.find_inpad_label(index)  # get link label if exists
            if (
                (label is None)
                or (
                    not exclude_named
                    and links.is_input(label)
                    and not is_stream_spec(label, True)
                )
                or (include_connected and is_stream_spec(label, True))
            ):
                yield (index, label, f)

    def _screen_output_pads(self, iter_pads, exclude_named):
        links = self._links
        for index, f in iter_pads():  # for each output pad
            labels = links.find_outpad_label(index)  # get link label if exists
            if labels is None or not len(labels):
                # unlabeled output pad
                yield (index, None, f)
            elif not exclude_named:
                # all labeled output pads are by definition named
                for label in labels:
                    # if multiple input link slots are reserved
                    # return for each slot
                    for _ in range(links.num_outputs(label)):
                        yield (index, label, f)

    def _iter_pads(
        self,
        chains: list[Filter],
        iter_filter_pad: Callable,
        i_first: int,
        pad: int | None,
        filter: int | None,
        exclude_chainable: bool,
        chainable_first: bool,
        include_connected: bool,
    ) -> Generator[tuple[PAD_INDEX, Filter]]:
        """Iterate over input pads of the filters on the filterchain

        :param filters: list of filters to iterate
        :param iter_filter_pad: Filter class function to iterate on filter pads
        :param pad: pad id
        :param filter: filter index
        :param chain: chain index
        :param exclude_chainable: True to leave out the last pads
        :param chainable_first: True to yield the last pad first then the rest
        :param include_connected: True to include pads connected to input streams, defaults to False
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        # iterate over all filters
        for cid, obj in enumerate(chains):
            for pidx, f in iter_filter_pad(
                obj,
                pad,
                filter,
                exclude_chainable=exclude_chainable,
                chainable_first=chainable_first,
                include_connected=include_connected,
            ):
                try:
                    yield (cid + i_first, *pidx), f
                except FiltergraphInvalidIndex:
                    pass

    def iter_input_pads(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: int | None = None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        exclude_named: bool = False,
    ) -> Generator[tuple[PAD_INDEX, Filter]]:
        """Iterate over input pads of the filters on the filtergraph

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last input pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last input first then the rest, defaults to False
        :param include_connected: True to include pads connected to input streams, defaults to False
        :param exclude_named: True to leave out named inputs, defaults to False to return only all inputs
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        if chain is None:
            # iterate over all filters
            chains = self.data
            i_first = 0
        else:
            try:
                chains = [self.data[chain]]
            except IndexError:
                raise FiltergraphInvalidIndex(f"Invalid {chain=} index.")
            i_first = chain

        return self._screen_input_pads(
            partial(
                self._iter_pads,
                chains,
                Chain.iter_input_pads,
                i_first,
                pad,
                filter,
                exclude_chainable,
                chainable_first,
                include_connected,
            ),
            exclude_named,
            include_connected,
        )

    def iter_output_pads(
        self,
        pad=None,
        filter=None,
        chain=None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        exclude_named: bool = False,
    ) -> Generator[tuple[PAD_INDEX, Filter]]:
        """Iterate over filtergraph's filter output pads

        :param exclude_named: True to leave out named outputs, defaults to False
        :type exclude_named: bool, optional
        :yield: filter pad index,  link label, and source filter object
        :rtype: tuple(tuple(int,int,int), str, Filter)
        """

        if chain is None:
            # iterate over all filters
            chains = self.data
            i_first = 0
        else:
            try:
                chains = [self.data[chain]]
            except IndexError:
                raise FiltergraphInvalidIndex(f"Invalid {chain=} index.")
            i_first = chain

        return self._screen_output_pads(
            partial(
                self._iter_pads,
                chains,
                Chain.iter_output_pads,
                i_first,
                pad,
                filter,
                exclude_chainable,
                chainable_first,
                include_connected,
            ),
            exclude_named,
        )

    def iter_chainable_input_pads(
        self,
        exclude_named: bool = False,
        include_connected: bool = False,
        chain: int | None = None,
    ) -> Generator[tuple[PAD_INDEX, Filter]]:
        """Iterate over filtergraph's chainable filter output pads

        :param exclude_named: True to leave out named input pads, defaults to False (all avail pads)
        :param include_connected: True to include input streams, which are already connected to input streams, defaults to False
        :yield: filter pad index, link label, & source filter object
        """

        # get all inputs
        def iter_pads():
            if chain is None:
                for cid, fchain in enumerate(self.data):
                    info = fchain.get_chainable_input_pad()
                    if info is not None:
                        yield (cid, *info[:2]), info[2]
            else:
                cid = chain + len(self.data) if chain < 0 else chain
                try:
                    info = self.data[chain].get_chainable_input_pad()
                    if info is not None:
                        yield (cid, *info[:2]), info[2]
                except:
                    pass

        return self._screen_input_pads(iter_pads, exclude_named, include_connected)

    def iter_chainable_output_pads(
        self, exclude_named=False, chain=None
    ) -> Generator[tuple[PAD_INDEX, Filter]]:
        """Iterate over filtergraph's chainable filter output pads

        :param exclude_named: True to leave out unnamed outputs, defaults to False
        :type exclude_named: bool, optional
        :yield: filter pad index, link label (if any), & source filter object
        :rtype: tuple(tuple(int,int,int), str, Filter)
        """

        def iter_pads():
            if chain is None:
                for cid, fchain in enumerate(self.data):
                    info = fchain.get_chainable_output_pad()
                    if info is not None:
                        yield ((cid, *info[:2]), info[2])
            else:
                cid = chain + len(self.data) if chain < 0 else chain
                try:
                    info = self.data[chain].get_chainable_output_pad()
                    if info is not None:
                        yield ((cid, *info[:2]), info[2])
                except:
                    pass

        return self._screen_output_pads(iter_pads, exclude_named)

    def get_num_inputs(self, chainable_only=False):
        return len(
            list(
                self.iter_chainable_input_pads()
                if chainable_only
                else self.iter_input_pads()
            )
        )

    def get_num_outputs(self, chainable_only=False):
        return len(
            list(
                self.iter_chainable_output_pads
                if chainable_only
                else self.iter_output_pads()
            )
        )

    def iter_input_labels(self) -> Generator[tuple[str, PAD_INDEX, PAD_INDEX | None]]:
        """iterate over the dangling labeled input pads of the filtergraph object

        :yield: a tuple of 3-tuple pad index and the pad index of the connected output pad if connected
        """
        for label, inpad, outpad in self._links.iter_inputs():
            yield label, inpad, outpad

    def iter_output_labels(self) -> Generator[tuple[str, PAD_INDEX, PAD_INDEX | None]]:
        """iterate over the dangling labeled output pads of the filtergraph object

        :yield: a tuple of 3-tuple pad index and the pad index of the connected input pad if connected
        """
        for label, outpad, inpad in self._links.iter_output_pads():
            if not ignore_connected or inpad is None:
                yield label, outpad, inpad

    def validate_input_index(self, inpad):
        try:
            GraphLinks.validate_pad_id_pair((inpad, None))
            for index in GraphLinks.iter_inpad_ids(inpad):
                self[index[0]].validate_input_index(*index[1:])
        except:
            raise Graph.InvalidFilterPadId("input", inpad)

    def validate_output_index(self, index):
        try:
            GraphLinks.validate_pad_id_pair((None, index))
            self[index[0]].validate_output_index(*index[1:])
        except:
            raise Graph.InvalidFilterPadId("output", index)

    def get_input_pad(self, index):
        """resolve (unconnected) input pad from pad index or label

        :param index: pad index or link label
        :type index: tuple(int,int,int) or str
        :return: filter input pad index and its link label (None if not assigned)
        :rtype: tuple(int,int,int), str|None

        Raises error if specified label does not resolve uniquely to an input pad
        """

        if isinstance(index, tuple):
            # given pad index
            inpad = index
            label = self._links.find_inpad_label(index)
            desc = f"input pad {index}"

            if label is not None and self._links[label][1] is not None:
                raise Graph.Error(f"{desc} is not an input label.")

        else:
            # given label
            desc = f"link label [{index}]"
            try:
                dsts, outpad = self._links[index]
            except:
                raise Graph.Error(f"{desc} does not exist.")

            if outpad is not None:
                raise Graph.Error(f"{desc} is not an input label.")

            dsts = [d for d in self._links.iter_inpad_ids(dsts)]
            n = len(dsts)

            if not n:
                raise Graph.Error(
                    f"no input pad found. specified {desc} is an output label."
                )

            if n > 1:
                raise Graph.Error(f"{desc} is associated with multiple input pads.")

            inpad = dsts[0]
            label = index

        if label is not None and is_stream_spec(label, True):
            raise Graph.Error(f"{desc} is already connected to an input stream.")

        # make sure the input pad is valid one on the fg (raises if fails)
        self.validate_input_index(inpad)

        return inpad, label

    def get_output_pad(self, index):
        """resolve (unconnected) output filter pad from pad index or labels

        :param index: pad index or link label
        :type index: tuple(int,int,int) or str
        :return: filter output pad index and its link labels
        :rtype: tuple(int,int,int), list(str)

        Raises error if specified index does not resolve uniquely to an output pad
        """

        if isinstance(index, str):
            # given label
            desc = f"link label [{index}]"
            try:
                outpad = self._links[index][1]
                assert outpad is not None
            except:
                raise Graph.Error(f"{desc} does not exist, or it is an input label.")
            label = index
        else:
            # given pad index
            desc = f"output pad {index}"
            outpad = index
            label = None
            labels = self._links.find_outpad_label(outpad)

            # if labels found, only 1 must be an output
            if len(labels):
                labels = [label for label in labels if not self._links.is_linked(label)]
                if len(labels) != 1:
                    raise Graph.Error(
                        f"{desc} is already labeled but associated to no ouput label or multiple output labels"
                    )
                label = labels[0]

        # make sure the output pad is valid (raises if fails)
        self.validate_output_index(outpad)

        return outpad, label

    def copy(self):
        return Graph(self)

    def are_linked(self, inpad, outpad):

        self._links.are_linked(inpad, outpad)

    def unlink(self, label=None, inpad=None, outpad=None):
        """unlink specified links

        :param label: specify all the links with this label, defaults to None
        :type label: str|int, optional
        :param inpad: specify the link with this inpad pad, defaults to None
        :type inpad: tuple(int,int,int), optional
        :param outpad: specify all the links with this outpad pad, defaults to None
        :type outpad: tuple(int,int,int), optional
        """
        self._links.unlink(label, inpad, outpad)

    def link(self, inpad, outpad, label=None, preserve_src_label=False, force=False):
        """set a filtergraph link

        :param inpad: input pad ids
        :type inpad: tuple(int,int,int)
        :param outpad: output pad index
        :type outpad: tuple(int,int,int)
        :param label: desired label name, defaults to None (=reuse inpad/outpad label or unnamed link)
        :type label: str, optional
        :param preserve_src_label: True to keep existing output labels of outpad, defaults to False
                                   to remove one output label of the outpad
        :type preserve_src_label: bool, optional
        :param force: True to drop conflicting existing link, defaults to False
        :type force: bool, optional
        :return: assigned label of the created link. Unnamed links gets a
                 unique integer value assigned to it.
        :rtype: str|int

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
            GraphLinks.validate_label(label, named_only=True, no_stream_spec=True)
        if inpad is not None:
            inpad = self.resolve_index(True, inpad)
            try:
                f = self.data[inpad[0]][inpad[1]]
                assert inpad[2] >= 0 and inpad[2] < f.get_num_inputs()
            except:
                raise Graph.InvalidFilterPadId("input", inpad)
        if outpad is not None:
            outpad = self.resolve_index(False, outpad)
            try:
                f = self.data[outpad[0]][outpad[1]]
                assert outpad[2] >= 0 and outpad[2] < f.get_num_outputs()
            except:
                raise Graph.InvalidFilterPadId("output", outpad)

        return self._links.link(inpad, outpad, label, preserve_src_label, force)

    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX | None = None,
        outpad: PAD_INDEX | None = None,
        force: bool = None,
    ):
        """label a filter pad

        :param label: name of the new label. Square brackets are optional.
        :type label: str
        :param inpad: input filter pad index or a sequence of pads, defaults to None
        :type inpad: tuple(int,int,int) | seq(tuple(int,int,int)), optional
        :param outpad: output filter pad index, defaults to None
        :type outpad: tuple(int,int,int), optional
        :param force: True to delete existing labels, defaults to None
        :type force: bool, optional
        :return: actual label name
        :rtype: str

        Only one of inpad and outpad argument must be given.

        If given label already exists, no new label will be created.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        if label[0] == "[" and label[-1] == "]":
            label = label[1:-1]

        GraphLinks.validate_label(
            label, named_only=True, no_stream_spec=outpad is not None
        )
        if inpad is not None:
            GraphLinks.validate_pad_id_pair((inpad, None))
            for d in GraphLinks.iter_inpad_ids(inpad):
                try:
                    f = self.data[d[0]][d[1]]
                    n = f.get_num_inputs()
                    assert d[2] >= 0 and d[2] < (n - 1 if d[1] > 0 else n)
                except:
                    raise Graph.InvalidFilterPadId("input", d)
        elif outpad is not None:
            GraphLinks.validate_pad_id(outpad)
            try:
                f = self.data[outpad[0]][outpad[1]]
                assert outpad[2] >= 0 and outpad[2] < f.get_num_outputs()
            except:
                raise Graph.InvalidFilterPadId("output", outpad)
        else:
            raise Graph.Error("filter pad index is not given")

        return self._links.create_label(label, inpad, outpad, force)

    def remove_label(self, label):
        """remove an input/output label

        :param label: linkn label
        :type label: str
        """

        self._links.remove_label(label)

    def rename_label(self, old_label, new_label):
        """rename an existing link label

        :param old_label: existing label named
        :type old_label: str
        :param new_label: new desired label name or None to make it unnamed label
        :type new_label: str|None
        :return: actual label name or None if unnamed
        :rtype: str|None

        Note:

        - `new_label` is not guaranteed, and actual label depends on existing labels

        """

        if not (isinstance(old_label, str) and old_label):
            raise Graph.Error(f"old_label [{old_label}] must be a string.")

        if new_label is not None and not (isinstance(new_label, str) and new_label):
            raise Graph.Error(f"new_label [{new_label}] must be None or a string.")

        # return the actual label or None if unnamed
        return new_label or self._links.rename(old_label, new_label)

    def split_sources(self):
        """possibly create a new filtergraph with all duplicate sources
           separated by split/asplit filter

        :return: _description_
        :rtype: _type_
        """

        # analyze the links to get a list of srcs which are connected to multiple inpad's/labels
        srcs_info = self._links.get_repeated_src_info()
        if not len(srcs_info):
            return self  # if none found, good to go as is

        # retrieve all the output pads of the filterchains
        chainable_outputs = [v[0] for v in self.iter_chainable_output_pads()]

        # create a clone to modify and output
        fg = Graph(self)

        # process each multi-destination outpad
        for outpad, dsts in srcs_info.items():

            # resolve stream media type
            try:
                media_type = fg[outpad[:2]].get_pad_media_type("o", outpad[2])
            except Filter.Unsupported as e:
                # if source filter pad media type cannot be resolved, try destination pads
                for inpad in dsts.values():
                    if isinstance(inpad, tuple):
                        try:
                            media_type = fg[inpad[:2]].get_pad_media_type("i", inpad[2])
                            e = None
                            break
                        except Filter.Unsupported:
                            pass
                if e is not None:
                    raise e

            # create the split filter
            split_filter = Filter(
                {"video": "split", "audio": "asplit"}[media_type],
                len(dsts),
            )

            # find `split` filter can be inserted to the outpad chain
            if outpad in chainable_outputs:
                # if it can, extend the chain
                fg[outpad[0]].append(split_filter)
                new_src = (outpad[0], outpad[1] + 1)
            else:
                # if not, append a new chain
                fg.append([split_filter])
                new_src = (len(fg) - 1, 0)
                # create a new link from outpad to split input
                fg._links.link(outpad, (*new_src, 0), force=True)

            # relink to inpad pad and label
            for pid, (label, index) in enumerate(dsts.items()):
                if isinstance(index, str):  # to output label
                    fg._links.add_label(label, inpad=(*new_src, pid), force=True)
                else:  # to input of a filter
                    fg._links.link((*new_src, pid), index, label=label, force=True)

        return fg

    def stack(
        self,
        other,
        auto_link=False,
        replace_sws_flags=None,
    ):
        """stack another Graph to this Graph

        :param other: other filtergraph
        :type other: Graph
        :param auto_link: True to connect matched I/O labels, defaults to None
        :type auto_link: bool, optional
        :param replace_sws_flags: True to use other's sws_flags if present,
                                  False to ignore other's sws_flags,
                                  None to throw an exception (default)
        :type replace_sws_flags: bool | None, optional
        :return: new filtergraph object
        :rtype: Graph

        * extend() and import links
        * If `auto-link=False`, common labels may be renamed.
        * For more explicit linking rather than the auto-linking, use `connect()` instead.

        TO-CHECK/TO-DO: what happens if common link labels are already linked
        """

        other = as_filtergraph_object(other)

        n = len(self)
        m = len(other)

        if not m:  # other is empty
            return Graph(self)
        if not n:  # self is empty
            return Graph(other)

        if isinstance(other, Graph):

            fg = Graph(self)
            if other.sws_flags is not None:
                if fg.sws_flags is None or replace_sws_flags is True:
                    fg.sws_flags = deepcopy(other.sws_flags)
                elif replace_sws_flags is None:
                    raise Graph.Error(
                        f"sws_flags are defined on both FilterGraphs. Specify replace_sws_flags option to True or False to avoid this error."
                    )
            fg._links.update(other._links, len(self), auto_link=auto_link)
            fg.data.extend(other)

        else:
            # if other is not filtergraph, copy and append the new chain
            fg = Graph(self)
            fg.append(other)

        return fg

    def connect(
        self,
        right,
        from_left,
        to_right,
        chain_siso=True,
        replace_sws_flags=None,
    ):
        """stack another Graph and make connection from left to right

        :param right: other filtergraph
        :type right: Graph
        :param from_left: output pad ids or labels of this fg
        :type from_left: seq(tuple(int,int,int)|str)
        :param to_right: input pad ids or labels of the `right` fg
        :type to_right: seq(tuple(int,int,int)|str)
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :type chain_siso: bool, optional
        :param replace_sws_flags: True to use `right` sws_flags if present,
                                  False to drop `right` sws_flags,
                                  None to throw an exception (default)
        :type replace_sws_flags: bool | None, optional
        :return: new filtergraph object
        :rtype: Graph

        * link labels may be auto-renamed if there is a conflict

        """

        # make sure right is a Graph object
        right = as_filtergraph(right, copy=True)

        # resolve from_left and to_right to pad ids (raises if invalid)
        srcs_info = [self.resolve_index(False, index) for index in from_left]
        nout = len(srcs_info)
        if nout != len(set(srcs_info)):
            raise ValueError(f"from_left pad indices are not unique.")

        dsts_info = [right.resolve_index(True, index) for index in to_right]
        ndst = len(dsts_info)
        if nout != len(set(dsts_info)):
            raise ValueError(f"to_right pad indices are not unique.")

        if nout != ndst:
            raise ValueError(f"from_left ({ndst}) and to_right ({nout}) do not match.")

        if nout == 0:
            raise ValueError(
                f"No pads are given in from_left and to_right. Use stack() if no linking is needed"
            )

        # get the labels
        srcs_info = [self.get_output_pad(index) for index in srcs_info]
        dsts_info = [right.get_input_pad(index) for index in dsts_info]

        # sift through the connections for chainable and unchainables
        link_pairs = []
        chain_pairs = []
        rm_chains = set()
        n0 = len(self)  # chain index offset

        for (inpad, dst_label), (outpad, src_label) in zip(dsts_info, srcs_info):
            new_dst = (inpad[0] + n0, *inpad[1:])

            do_chain = (
                chain_siso
                and self.data[outpad[0]][outpad[1]].get_num_outputs() == 1
                and right.data[inpad[0]][inpad[1]].get_num_inputs() == 1
            )

            if do_chain:
                if dst_label is not None:
                    right._links.remove_label(dst_label, inpad)
                chain_pairs.append((new_dst, outpad, src_label))
                rm_chains.add(new_dst[0])
            else:
                # reuse the outpad or inpad label if given
                link_pairs.append((new_dst, outpad, src_label or dst_label))

        # stack 2 filtergraphs
        fg = self.stack(right, False, replace_sws_flags)

        if nout > 0:
            # link marked chains
            for link_args in link_pairs:
                fg._links.link(*link_args)

            # combine chainable chains
            for inpad, outpad, src_label in reversed(
                sorted(chain_pairs, key=lambda v: v[1])
            ):
                fc_src = fg[outpad[0]]
                n_src = len(fc_src)
                fc_src.extend(fg.pop(inpad[0]))
                if src_label is not None:
                    fg._links.remove_label(src_label)
                fg._links.merge_chains(inpad[0], outpad[0], n_src)
            fg._links.remove_chains(rm_chains)

        return fg

    def _iter_io_pads(self, is_input, how, ignore_labels=False):
        """Iterates input/output pads of the filtergraph

        :param is_input: True if input; False if output
        :type is_input: bool
        :param how: pad selection method

                    -----------  -------------------------------------------------------------------
                    'chainable'  only chainable pads.
                    'per_chain'  one pad per chain. Source and sink chains are ignored.
                    'all'        joins all input pads and output pads
                    -----------  -------------------------------------------------------------------

        :type how: "chainable"|"per_chain"|"all"
        :param ignore_labels: True to return labaled (but not linked) pads, defaults to False
        :type ignore_labels: bool, optional
        :yield: pad index, pad label, parent filter
        :rtype: tuple(tuple(int,int,int), label, Filter)
        """
        if how is None or how in ("per_chain", "all"):
            generator = self.iter_input_pads if is_input else self.iter_output_pads

            return (
                generator()
                if how == "all"
                else (
                    info
                    for info in (
                        next(generator(exclude_named=not ignore_labels, chain=c), None)
                        for c in range(len(self.data))
                    )
                    if info is not None
                )
            )
        elif how == "chainable":
            return (
                self.iter_chainable_input_pads
                if is_input
                else self.iter_chainable_output_pads
            )(exclude_named=not ignore_labels)
        else:
            raise ValueError(f"unknown how argument value: {how}")

    def join(
        self,
        right,
        how="per_chain",
        match_scalar=False,
        ignore_labels=False,
        chain_siso=True,
        replace_sws_flags=None,
    ):
        """append another Graph object and connect all inputs to the outputs of this filtergraph

        :param right: right filtergraph to be appended
        :type right: Graph|Chain|Filter
        :param how: method on how to mate input and output, defaults to "per_chain".

            ===========  ===================================================================
            'chainable'  joins only chainable input pads and output pads.
            'per_chain'  joins one pair of first available input pad and output pad of each
                         mating chains. Source and sink chains are ignored.
            'all'        joins all input pads and output pads
            'auto'       tries 'per_chain' first, if fails, then tries 'all'.
            ===========  ===================================================================

        :type how: "chainable"|"per_chain"|"all"
        :param match_scalar: True to multiply self if SO-MI connection or right if MO-SI connection
                              to single-ended entity to the other, defaults to False
        :type match_scalar: bool
        :param ignore_labels: True to pair pads w/out checking pad labels, default: True
        :type ignore_labels: bool, optional
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :type chain_siso: bool, optional
        :param replace_sws_flags: True to use other's sws_flags if present,
                                  False to ignore other's sws_flags,
                                  None to throw an exception (default)
        :type replace_sws_flags: bool | None, optional
        :return: Graph with the appended filter chains or None if inplace=True.
        :rtype: Graph or None
        """

        # make sure right is a Graph, Chain, or Filter object
        right = as_filtergraph(right)

        if not len(right):
            return Graph(self)

        if not len(self):
            return Graph(right)

        # auto-mode, 1-deep recursion
        if how == "auto":
            try:
                return self.join(
                    right,
                    "per_chain",
                    match_scalar,
                    ignore_labels,
                    chain_siso,
                    replace_sws_flags,
                )
            except:
                return self.join(
                    right,
                    "all",
                    match_scalar,
                    ignore_labels,
                    chain_siso,
                    replace_sws_flags,
                )

        # list all the unconnected output pads of left fg
        # [(index, label, filter)]
        src_info = tuple(self._iter_io_pads(False, how, ignore_labels))

        # list all the unconnected input pads of right fg
        dst_info = tuple(right._iter_io_pads(True, how, ignore_labels))

        # to join, the number of pads must match
        nsrc = len(src_info)
        ndst = len(dst_info)

        if nsrc != ndst:

            if match_scalar and ndst == 1:
                # multiply right to match self
                right = right * nsrc
                dst_info = right._iter_io_pads(True, how)
            elif match_scalar and nsrc == 1:
                # multiply self to match right
                self = self * ndst
                src_info = self._iter_io_pads(False, how)
            else:
                raise FiltergraphMismatchError(nsrc, ndst)

        return self.connect(
            right,
            [index for index, *_ in src_info],
            [index for index, *_ in dst_info],
            chain_siso,
            replace_sws_flags,
        )

    def attach(self, right, left_on=None, right_on=None):
        """attach an output pad to right's input pad

        :param right: output filterchain to be attached
        :type right: Chain or Filter
        :param left_on: pad_index, specify the pad on self, default to None (first available)
        :type left_on: int or str, optional
        :param right_on: pad index, specifies which pad on the right graph, defaults to None (first available)
        :type right_on: int or str, optional
        :return: new filtergraph object
        :rtype: Graph

        """

        right = as_filtergraph_object(right)
        right_on = right.resolve_index(True, right_on)
        left_on = self.resolve_index(False, left_on)
        return self.connect(right, [left_on], [right_on], chain_siso=True)

    def rattach(self, left, right_on=None, left_on=None):
        """prepend an input filterchain to an existing filter chain of the filtergraph

        :param left: filterchain to be attached
        :type left: Chain or Filter
        :param right_on: filterchain to accept the input chain, defaults to None (first available)
        :type right_on: int or str, optional
        :return: new filtergraph object
        :rtype: Graph

        If the attached filter pad has an assigned label, the label will be automatically removed.

        """

        left = as_filtergraph(left)
        left_on = left.resolve_index(False, left_on)
        right_on = self.resolve_index(True, right_on)
        return left.connect(self, [left_on], [right_on], chain_siso=True)

    @contextmanager
    def as_script_file(self):
        """return script file containing the filtergraph description

        :yield: path of a temporary text file with filtergraph description
        :rtype: str

        This method is intended to work with the `filter_script` and
        `filter_complex_script` FFmpeg options, by creating a temporary text file
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

          Note that ``pipe:0`` must be used and not the shorthand ``'-'`` unlike
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
