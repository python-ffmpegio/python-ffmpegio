from __future__ import annotations

from collections import UserList
from collections.abc import Generator, Callable
from contextlib import contextmanager
from functools import partial, reduce
from copy import deepcopy
from math import floor, log10
import os
from tempfile import NamedTemporaryFile

from ..utils import filter as filter_utils, is_stream_spec
from .. import filtergraph as fgb

from .typing import *
from .exceptions import *
from .GraphLinks import GraphLinks


__all__ = ["Graph"]


class Graph(UserList, fgb.abc.FilterGraphObject):
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

    _unc_label: str = "UNC"

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
        elif isinstance(filter_specs, fgb.Chain):
            filter_specs = [filter_specs] if len(filter_specs) else ()
        elif isinstance(filter_specs, fgb.Filter):
            filter_specs = [[filter_specs]]

        super().__init__(
            ()
            if filter_specs is None or not len(filter_specs)
            else (fgb.Chain(fspec) for fspec in filter_specs)
        )

        self._links = GraphLinks(links)
        """utils.fglinks.GraphLinks: filtergraph link specifications
        """

        self.sws_flags = (
            None if sws_flags is None else fgb.Filter(["scale", *sws_flags])
        )
        """Filter|None: swscale flags for automatically inserted scalers
        """

        self.autosplit_output = autosplit_output
        """bool: True to insert a split filter when an output pad is linked multiple times. default: True """

    def _resolve_pad_index(
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
        """Resolve unconnected label or pad index to full 3-element pad index

        :param index_or_label: pad index set or pad label or ``None`` to auto-select
        :param is_input: True to resolve an input pad, else an output pad, defaults to True
        :param chain_id_omittable: True to allow ``None`` chain index, defaults to False
        :param filter_id_omittable: True to allow ``None`` filter index, defaults to False
        :param pad_id_omittable: True to allow ``None`` pad index, defaults to False
        :param resolve_omitted: True to fill each omitted value with the prescribed fill value.
        :param chain_fill_value: if ``chain_id_omittable=True`` and chain index is either not
                                 given or ``None``, this value will be returned, defaults to None,
                                 which returns the first available pad.
        :param filter_fill_value:if ``filter_id_omittable=True`` and filter index is either not
                                 given or ``None``, this value will be returned, defaults to None,
                                 which returns the first available pad.
        :param pad_fill_value: if ``pad_id_omittable=True`` and either ``index`` is None or
                               pad index is ``None``, this value will be returned, defaults to None,
                               which returns the first available pad.
        :param chainable_first: if True, chainable pad is selected first, defaults to False

        One and only one of ``index`` and ``label`` must be specified. If the given index
        or label is invalid, it raises FiltergraphPadNotFoundError.
        """

        # obtain 3-element tuple index (unvalidated)
        index = super()._resolve_pad_index(
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
                        chain=k, filter=j, pad=i, unlabeled_only=index is None
                    )
                )
            return pad[0]
        except:
            raise FiltergraphPadNotFoundError("input" if is_input else "output", index)

    def __str__(self) -> str:
        # insert split filters if autosplit_output is True
        fg = self.split_sources() if self.autosplit_output else self

        # label unconnected pads
        label = self._unc_label
        unc_pads = {}
        i = j = 0
        for i, (index, _, _) in enumerate(self.iter_input_pads(unlabeled_only=True)):
            unc_pads[f"{label}{i}"] = (index, None)
        for j, (index, _, _) in enumerate(self.iter_output_pads(unlabeled_only=True)):
            unc_pads[f"{label}{i+j+1}"] = (None, index)

        links = {**fg._links, **unc_pads} if i or j else fg._links

        return filter_utils.compose_graph(fg, links, fg.sws_flags and fg.sws_flags[1:])

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
        super().__setitem__(key, fgb.as_filterchain(value, copy=True))
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
        self.data.append(fgb.as_filterchain(item, copy=True))

    def extend(self, other, auto_link=False, force_link=False):
        other = fgb.as_filtergraph(other)
        self._links.update(
            other._links, len(self), auto_link=auto_link, force=force_link
        )
        self.data.extend(other)

    def insert(self, i, item):
        self.data.insert(i, fgb.as_filterchain(item))
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

    def __add__(self, other):
        # join
        try:
            other = fgb.as_filtergraph_object(other)
        except Exception:
            return NotImplemented
        return self.join(other, "auto")

    def __radd__(self, other):
        # join
        try:
            other = fgb.as_filtergraph(other)
        except Exception:
            return NotImplemented
        return other.join(self, "auto")

    def __or__(self, other):
        # create filtergraph with self and other as parallel chains, self first

        try:
            other = fgb.as_filtergraph_object(other)
        except:
            return NotImplemented
        return self.stack(other)

    def __ror__(self, other):
        # create filtergraph with self and other as parallel chains, self last
        try:
            other = fgb.as_filtergraph(other)
        except:
            return NotImplemented
        return other.stack(self)

    def _chain(
        self,
        on_left: bool,
        other: fgb.abc.FilterGraphObject,
        chain_id: int,
        other_chain_id: int,
    ) -> fgb.Chain | fgb.Graph:
        """chain self->other (no var check)

        :param other: the other filitergraph object to chain together
        :param on_left: True if this object's output is connecting to the other
        :param chain_id: chain id of self, nonzero only if self is a ``Graph``
        :param other_chain_id: chain of other, nonzero only if other is a ``Graph``
        :return: ``Graph`` object if either self or other is a ``Graph`` else ``Chain``
        """

        left, right = (self, other) if on_left else (other, self)
        left_id, right_id = (
            (chain_id, other_chain_id) if on_left else (other_chain_id, chain_id)
        )
        return left._attach(on_left, right, (left_id, -1, -1), (right_id, 0, -1))

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
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter, PAD_INDEX | str | None]]:
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

            for pidx, f, other_pidx in iter_filter_pad(
                c,
                pad,
                filter,
                exclude_chainable=exclude_chainable,
                chainable_first=chainable_first,
                include_connected=include_connected,
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
                if (is_str and unlabeled_only) or not (is_str or include_connected):
                    continue

                yield index, f, other_pidx

    def iter_input_pads(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: int | None = None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        unlabeled_only: bool = False,
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter, PAD_INDEX | str | None]]:
        """Iterate over input pads of the filters on the filtergraph

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last input pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last input first then the rest, defaults to False
        :param include_connected: True to include pads connected to input streams, defaults to False
        :param unlabeled_only: True to leave out named inputs, defaults to False to return only all inputs
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        for index, f, other_pidx in self._iter_pads(
            fgb.Chain.iter_input_pads,
            self._links.input_dict(),
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
            unlabeled_only,
        ):
            # exclude a pad connected to an input stream
            if (
                not include_connected
                and isinstance(other_pidx, str)
                and is_stream_spec(other_pidx)
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
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter, PAD_INDEX | str | None]]:
        """Iterate over filtergraph's filter output pads

        :param unlabeled_only: True to leave out named outputs, defaults to False
        :type unlabeled_only: bool, optional
        :yield: filter pad index,  link label, and source filter object
        :rtype: tuple(tuple(int,int,int), str, Filter)
        """

        for v in self._iter_pads(
            fgb.Chain.iter_output_pads,
            self._links.output_dict(),
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
            unlabeled_only,
        ):
            yield v

    def iter_chainable_input_pads(
        self,
        unlabeled_only: bool = False,
        include_connected: bool = False,
        chain: int | None = None,
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter]]:
        """Iterate over filtergraph's chainable filter output pads

        :param unlabeled_only: True to leave out named input pads, defaults to False (all avail pads)
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

        return self._screen_input_pads(iter_pads, unlabeled_only, include_connected)

    def iter_chainable_output_pads(
        self, unlabeled_only=False, chain=None
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter]]:
        """Iterate over filtergraph's chainable filter output pads

        :param unlabeled_only: True to leave out unnamed outputs, defaults to False
        :type unlabeled_only: bool, optional
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

        return self._screen_output_pads(iter_pads, unlabeled_only)

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

    def iter_input_labels(
        self, exclude_stream_specs: bool = False
    ) -> Generator[tuple[str, PAD_INDEX]]:
        """iterate over the dangling labeled input pads of the filtergraph object

        :param exclude_stream_specs: True to not include input streams
        :yield: a tuple of 3-tuple pad index and the pad index of the connected output pad if connected
        """
        for label_index in self._links.iter_inputs(exclude_stream_specs):
            yield label_index

    def iter_output_labels(self) -> Generator[tuple[str, PAD_INDEX]]:
        """iterate over the dangling labeled output pads of the filtergraph object

        :yield: a tuple of 3-tuple pad index and the pad index of the connected input pad if connected
        """
        for label_index in self._links.iter_outputs():
            yield label_index

    def get_input_pad(
        self, index_or_label: PAD_INDEX | str
    ) -> tuple[PAD_INDEX, str | None]:
        """resolve (unconnected) input pad from pad index or label

        :param index: pad index or link label
        :return: filter input pad index and its link label (None if not assigned)

        Raises error if specified label does not resolve uniquely to an input pad
        """

        index = self._resolve_pad_index(index_or_label, is_input=True)
        return index, self.get_label(inpad=index)

    def get_output_pad(
        self, index_or_label: PAD_INDEX | str
    ) -> tuple[PAD_INDEX, str | None]:
        """resolve (unconnected) output filter pad from pad index or labels

        :param index: pad index or link label
        :type index: tuple(int,int,int) or str
        :return: filter output pad index and its link labels
        :rtype: tuple(int,int,int), list(str)

        Raises error if specified index does not resolve uniquely to an output pad
        """

        index = self._resolve_pad_index(index_or_label, is_input=False)
        return index, self.get_label(outpad=index)

    def copy(self):
        return Graph(self)

    def are_linked(
        self,
        inpad: PAD_INDEX | None,
        outpad: PAD_INDEX | None,
        check_input_stream: bool | str = False,
    ) -> bool:
        """True if given pads are linked

        :param inpad: input pad index, default to ``None`` to check if ``outpad`` is connected to any
                      input pad.
        :param outpad: output pad index, defaults to ``None`` to check if ``inpad`` is connected to any
                       output pad or an input stream.
        :param check_input_stream: True to check inpad is connected to an input stream, or a stream
                                   specifier string to check the connection to a specific stream, defaults
                                   to ``False``.

        ``ValueError`` will be raised if both ``inpad`` and ``outpad`` ``None`` or
        if ``include_input_stream!=False`` and ``outpad`` is ``None``.

        """

        try:
            return self._links.are_linked(inpad, outpad, check_input_stream)
        except ValueError:
            raise

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
            inpad = self._resolve_pad_index(inpad, is_input=True)
            try:
                f = self.data[inpad[0]][inpad[1]]
                assert inpad[2] >= 0 and inpad[2] < f.get_num_inputs()
            except:
                raise Graph.InvalidFilterPadId("input", inpad)
        if outpad is not None:
            outpad = self._resolve_pad_index(outpad, is_input=False)
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
        left_info = self._links.get_repeated_src_info()
        if not len(left_info):
            return self  # if none found, good to go as is

        # retrieve all the output pads of the filterchains
        chainable_outputs = [v[0] for v in self.iter_chainable_output_pads()]

        # create a clone to modify and output
        fg = Graph(self)

        # process each multi-destination outpad
        for outpad, dsts in left_info.items():

            # resolve stream media type
            try:
                media_type = fg[outpad[:2]].get_pad_media_type("o", outpad[2])
            except fgb.Filter.Unsupported as e:
                # if source filter pad media type cannot be resolved, try destination pads
                for inpad in dsts.values():
                    if isinstance(inpad, tuple):
                        try:
                            media_type = fg[inpad[:2]].get_pad_media_type("i", inpad[2])
                            e = None
                            break
                        except fgb.Filter.Unsupported:
                            pass
                if e is not None:
                    raise e

            # create the split filter
            split_filter = fgb.Filter(
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

        other = fgb.as_filtergraph_object(other)

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
        right: fgb.abc.FilterGraphObject,
        from_left: PAD_INDEX,
        to_right: PAD_INDEX,
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
        right = fgb.as_filtergraph(right, copy=True)

        # resolve from_left and to_right to pad ids (raises if invalid)
        left_info = [
            self._resolve_pad_index(index, is_input=False) for index in from_left
        ]
        nout = len(left_info)
        if nout != len(set(left_info)):
            raise ValueError(f"from_left pad indices are not unique.")

        right_info = [
            right._resolve_pad_index(index, is_input=True) for index in to_right
        ]
        ndst = len(right_info)
        if nout != len(set(right_info)):
            raise ValueError(f"to_right pad indices are not unique.")

        if nout != ndst:
            raise ValueError(f"from_left ({ndst}) and to_right ({nout}) do not match.")

        if nout == 0:
            raise ValueError(
                f"No pads are given in from_left and to_right. Use stack() if no linking is needed"
            )

        return self._connect(
            right, left_info, right_info, chain_siso, replace_sws_flags
        )

    def _connect(
        self,
        right: fgb.abc.FilterGraphObject,
        right_indices: list[PAD_INDEX],
        left_indices: list[PAD_INDEX],
        chain_siso: bool = True,
        replace_sws_flags: bool | None = None,
    ) -> fgb.Graph:
        """stack another Graph and make connection from left to right (no var checks)

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

        # get the labels
        left_info = [self.get_output_pad(index) for index in left_indices]
        right_info = [right.get_input_pad(index) for index in right_indices]

        # sift through the connections for chainable and unchainables
        link_pairs = []
        chain_pairs = []
        rm_chains = set()
        n0 = len(self)  # chain index offset

        for (inpad, dst_label), (outpad, src_label) in zip(right_info, left_info):
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
                        next(generator(unlabeled_only=not ignore_labels, chain=c), None)
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
            )(unlabeled_only=not ignore_labels)
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
        right = fgb.as_filtergraph(right)

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

    def attach(
        self,
        right: fgb.abc.FilterGraphObject,
        left_on: PAD_INDEX | None = None,
        right_on: PAD_INDEX | None = None,
    ):
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

        right = fgb.as_filtergraph_object(right)
        right_on = right._resolve_pad_index(
            right_on,
            is_input=True,
            chain_id_omittable=True,
            filter_id_omittable=True,
            pad_id_omittable=True,
        )
        left_on = self._resolve_pad_index(left_on, is_input=False)
        return self._attach(True, right, left_on, right_on)

    def rattach(
        self,
        left: fgb.abc.FilterGraphObject,
        right_on: PAD_INDEX | None = None,
        left_on: PAD_INDEX | None = None,
    ):
        """prepend an input filterchain to an existing filter chain of the filtergraph

        :param left: filterchain to be attached
        :type left: Chain or Filter
        :param right_on: filterchain to accept the input chain, defaults to None (first available)
        :type right_on: int or str, optional
        :return: new filtergraph object
        :rtype: Graph

        If the attached filter pad has an assigned label, the label will be automatically removed.

        """

        left = fgb.as_filtergraph(left)
        left_on = left._resolve_pad_index(left_on, is_input=False)
        right_on = self._resolve_pad_index(right_on, is_input=True)
        return left.connect(self, [left_on], [right_on], chain_siso=True)

    def _attach(
        self,
        is_input: bool,
        other: fgb.abc.FilterGraphObject,
        index: PAD_INDEX | list[PAD_INDEX],
        other_index: PAD_INDEX | list[PAD_INDEX],
    ) -> fgb.Chain | fgb.Graph:
        """helper function attach other filtergraph to this graph (no var check)

        :param is_input: True to attach other to the right
        :param other: other filtergraph object to attach
        :param index: full pad index of this object to attach the other. If multiple
                      links must be made, supply all the indices as a list
        :param other_index: full pad index of the other object to  be attached to this.
                            If multiple links must be made, supply all the indices
                            as a list.
        :return: Joined filtergraph object
        """

        if not isinstance(index, list):
            index = [index]
        if not isinstance(other_index, list):
            other_index = [other_index]

        left, right, left_indices, right_indices = (
            (self, other, index, other_index)
            if is_input
            else (other, self, other_index, index)
        )
        return left._connect(right, right_indices, left_indices)

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

    def _input_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """returns True if specified input pad index is available"""

        # check linked indices
        if any(
            link[1] == index
            for link in self._links.iter_links(include_input_stream=True)
        ):
            # already connected
            return False

        # check the chain
        return self[index[0]]._input_pad_is_available((0, *index[1:]))

    def _output_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """returns True if specified output pad index is available"""

        # check linked indices
        if any(link[2] == index for link in self._links.iter_links()):
            # already connected
            return False

        return self[index[0]]._output_pad_is_available((0, *index[1:]))

    def _check_partial_pad_index(
        self, index: tuple[int | None, int | None, int | None], is_input: bool
    ) -> bool:
        """True if defined values of the partial pad index are valid"""

        chain = index[0]
        if chain is not None and (chain < 0 or chain >= len(self)):
            return False

        return any(
            c._check_partial_pad_index((None, *index[1:]), is_input) for c in self
        )

    def _input_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified input pad is chainable"""

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
        """True if specified output pad is chainable"""

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
