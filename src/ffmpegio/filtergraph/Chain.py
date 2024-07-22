from __future__ import annotations

from collections import UserList
from collections.abc import Callable, Generator
from functools import reduce

from ..utils import filter as filter_utils
from .. import filtergraph as ffg

from .typing import *
from .exceptions import *


__all__ = ["Chain"]


class Chain(UserList, ffg.abc.FilterGraphObject):
    """List of FFmpeg filters, connected in series

    Chain() to instantiate empty Graph object

    Chain(obj) to copy-instantiate Graph object from another

    Chain('...') to parse an FFmpeg filtergraph expression

    :param filter_specs: single-in-single-out filtergraph description without
                         labels, defaults to None
    :type filter_specs: str or seq(Filter), optional
    """

    class Error(FFmpegioError):
        pass

    def __init__(self, filter_specs=None):
        # convert str to a list of filter_specs
        if isinstance(filter_specs, str):
            filter_specs, links, sws_flags = filter_utils.parse_graph(filter_specs)
            if links:
                raise ValueError(
                    "filter_specs with link labels cannot be represented by the Chain class. Use Graph."
                )
            if sws_flags:
                raise ValueError(
                    "filter_specs with sws_flags cannot be represented by the Chain class. Use Graph."
                )
            if len(filter_specs) != 1:
                raise ValueError(
                    "filter_specs str must resolve to a single-chain filtergraph. Use the Graph class instead."
                )
            filter_specs = filter_specs[0]
        elif isinstance(filter_specs, ffg.Filter):
            filter_specs = [filter_specs]

        super().__init__(
            ()
            if filter_specs is None
            else (ffg.as_filter(fspec) for fspec in filter_specs)
        )

    def __str__(self):
        return filter_utils.compose_graph([self.data])

    def __repr__(self):
        type_ = type(self)
        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{str(self)}\"
    Number of filters: {len(self.data)}
    Input pads ({self.get_num_inputs()}): {', '.join((str(id) for id,_ in self.iter_input_pads()))}
    Output pads: ({self.get_num_outputs()}): {', '.join((str(id) for id,_ in self.iter_output_pads()))}
"""

    def __setitem__(self, key, value):
        super().__setitem__(key, ffg.as_filter(value))

    def append(self, item):
        return super().append(ffg.as_filter(item))

    def extend(self, other):
        return super().extend([ffg.as_filter(f) for f in other])

    def insert(self, i, item):
        return super().insert(i, ffg.as_filter(item))

    def __contains__(self, item):
        item = ffg.as_filter(item)
        return any((f.name == item for f in self.data))

    def __mul__(self, __n):
        return ffg.Graph([self] * __n) if isinstance(__n, int) else NotImplemented

    def __add__(self, other: ffg.Filter | ffg.Chain | str) -> Chain | ffg.Graph:

        # grab the next available index, prefer chainable
        index = self._resolve_pad_index(
            None,
            is_input=False,
            chain_id_omittable=True,
            filter_id_omittable=True,
            pad_id_omittable=True,
            chainable_first=True,
        )

        # try to convert the other filtergraph object as a chain
        try:
            other = ffg.as_filterchain(other)
        except FiltergraphConversionError:
            return NotImplemented

        # grab the next available index, prefer chainable
        other_index = self._resolve_pad_index(
            None,
            is_input=True,
            chain_id_omittable=True,
            filter_id_omittable=True,
            pad_id_omittable=True,
            chainable_first=True,
        )

        return (
            Chain([*self, *other])
            if self._output_pad_is_chainable(index)
            and other._input_pad_is_chainable(other_index)
            else ffg.Graph([self]).connect(other, index, other_index)
        )

    def __radd__(self, other: ffg.Filter | ffg.Chain | str) -> Chain | ffg.Graph:

        # grab the next available index, prefer chainable
        index = self._resolve_pad_index(
            None,
            is_input=True,
            chain_id_omittable=True,
            filter_id_omittable=True,
            pad_id_omittable=True,
            chainable_first=True,
        )

        # try to convert the other filtergraph object as a chain
        try:
            other = ffg.as_filterchain(other)
        except FiltergraphConversionError:
            return NotImplemented

        # grab the next available index, prefer chainable
        other_index = self._resolve_pad_index(
            None,
            is_input=False,
            chain_id_omittable=True,
            filter_id_omittable=True,
            pad_id_omittable=True,
            chainable_first=True,
        )

        return (
            Chain([*other, *self])
            if self._output_pad_is_chainable(other_index)
            and other._input_pad_is_chainable(index)
            else ffg.Graph([other]).connect(self, other_index, index)
        )

    def __mul__(self, __n):
        if len(self):
            return ffg.Graph([self] * __n) if isinstance(__n, int) else NotImplemented
        else:
            return Chain(self)

    def __rmul__(self, __n):
        if len(self):
            return ffg.Graph([self] * __n) if isinstance(__n, int) else NotImplemented
        else:
            return Chain(self)

    def __or__(self, other):
        # create filtergraph with self and other as parallel chains, self first

        try:
            other = ffg.as_filterchain(other)
        except:
            return NotImplemented

        n = len(self)
        m = len(other)
        return ffg.Graph([self, other]) if n and m else self if n else other

    def __ror__(self, other):
        # create filtergraph with self and other as parallel chains, self last

        try:
            other = ffg.as_filterchain(other)
        except:
            return NotImplemented

        n = len(self)
        m = len(other)
        return ffg.Graph([other, self]) if n and m else self if n else other

    def _chain(
        self, other: ffg.abc.FilterGraphObject, chain_id: int, other_chain_id: int
    ) -> Chain | ffg.Graph:
        """chain self->other (no var check)

        :param other: the other filitergraph object to chain to
        :param chain_id: chain id of self, nonzero only if self is a ``Graph``
        :param other_chain_id: chain of other, nonzero only if other is a ``Graph``
        :return: ``Graph`` object if either self or other is a ``Graph`` else ``Chain``
        """

        if isinstance(other, ffg.Graph):
            return other._rchain(self, other_chain_id, chain_id)
        else:
            if not chain_id or not other_chain_id:
                raise ValueError("chain_id and other_chain_id must be zero")
            return Chain(
                [*self, other] if isinstance(other, ffg.Filter) else [*self, *other]
            )

    def _rchain(
        self, other: ffg.abc.FilterGraphObject, chain_id: int, other_chain_id: int
    ) -> Chain | ffg.Graph:
        """chain other->self (no var check)

        :param other: the other filitergraph object to chain to
        :param chain_index: chain id of self, nonzero only if self is a ``Graph``
        :param other_chain_index: chain of other, nonzero only if other is a ``Graph``
        :return: ``Graph`` object if either self or other is a ``Graph`` else ``Chain``
        """

        if isinstance(other, ffg.Filter):
            if not chain_id or not other_chain_id:
                raise ValueError("chain_id and other_chain_id must be zero")
            return Chain([other, self])
        else:
            return other._chain(self, other_chain_id, chain_id)

    def __mul__(self, __n):
        if not isinstance(__n, int):
            return NotImplemented
        if not len(self.data):
            return Chain(self)
        fg = ffg.Graph([self])
        return reduce(fg.stack, [self] * (__n - 1), fg)

    def __rmul__(self, __n):
        return self.__mul__(__n)

    def __iadd__(self, other):
        fg = self + other
        if type(fg) != Chain:
            raise Chain.Error(
                "cannot assign operation outcome which is not a filterchain"
            )
        self.data = fg.data
        return self

    def __irshift__(self, other):
        fg = self >> other
        if type(fg) != Chain:
            raise Chain.Error(
                "cannot assign operation outcome which is not a filterchain"
            )
        self.data = fg.data
        return self

    def _iter_pads(
        self,
        filters: list[ffg.Filter],
        iter_filter_pad: Callable,
        i_first: int,
        i_nochain: int,
        pad: int | None,
        chain: Literal[0] | None,
        exclude_chainable: bool,
        chainable_first: bool,
        include_connected: bool,
    ) -> Generator[tuple[PAD_INDEX, ffg.Filter, PAD_INDEX | None]]:
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

        if isinstance(chain, int) and chain != 0:
            # Filterchain has only one chain.
            raise FiltergraphInvalidIndex(f"Invalid {chain=} index")

        # iterate over all filters
        for i, f in enumerate(filters):
            for pidx, f in iter_filter_pad(
                f,
                pad,
                exclude_chainable=not include_connected
                and (exclude_chainable or i != i_nochain),
                chainable_first=chainable_first,
            ):
                yield (i + i_first, *pidx), f

    def iter_input_pads(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: Literal[0] | None = None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        exclude_named: bool = False,
    ) -> Generator[tuple[PAD_INDEX, ffg.Filter, PAD_INDEX | None]]:
        """Iterate over input pads of the filters on the filterchain

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last input pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last input first then the rest, defaults to False
        :param exclude_named: True to leave out named inputs, defaults to False to return only all inputs
        :param include_connected: True to include pads connected to input streams, defaults to False
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        if filter is None:
            # iterate over all filters
            filters = self.data
            i_first = 0
        else:
            try:
                filters = [self.data[filter]]
            except IndexError:
                raise FiltergraphInvalidIndex(f"Invalid {filter=} index.")
            i_first = filter

        for v in self._iter_pads(
            filters,
            ffg.Filter.iter_input_pads,
            i_first,
            0,
            pad,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
        ):
            try:
                yield v
            except FiltergraphInvalidIndex:
                pass

    def iter_output_pads(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: int | None = None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        exclude_named: bool = False,
    ) -> Generator[tuple[PAD_INDEX, ffg.Filter, PAD_INDEX | None]]:
        """Iterate over output pads of the filters on the filterchain

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last output pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last output first then the rest, defaults to False
        :param include_connected: True to include pads connected to output streams, defaults to False
        :param exclude_named: True to leave out named outputs, defaults to False to return only all inputs
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        if filter is None:
            # iterate over all filters
            filters = self.data
            i_first = 0
        else:
            try:
                filters = [self.data[filter]]
            except IndexError:
                raise FiltergraphInvalidIndex(f"Invalid {filter=} index")
            i_first = filter

        for v in self._iter_pads(
            filters,
            ffg.Filter.iter_output_pads,
            i_first,
            len(self.data) - 1,
            pad,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
        ):
            yield v

    def get_chainable_input_pad(self) -> tuple[PAD_INDEX, ffg.Filter] | None:
        """get first filter's input pad, which can be chained

        :return: filter position, input pad poisition, and filter object.
                 If the head filter is a source filter, returns None.
        """

        if not len(self):
            return None
        f = self[-1]
        nin = f.get_num_inputs()
        return ((0, nin - 1), f) if nin else None

    def get_chainable_output_pad(self) -> tuple[PAD_INDEX, ffg.Filter] | None:
        """get last filter's output pad, which can be chained

        :return: filter position, output pad poisition, and filter object.
                 If the tail filter is a sink filter, returns None.
        """

        if not len(self):
            return None
        f = self[-1]
        nout = f.get_num_outputs()
        return ((len(self) - 1, nout - 1), f) if nout else None

    def get_num_inputs(self) -> int:
        return len(list(self.iter_input_pads()))

    def get_num_outputs(self) -> int:
        return len(list(self.iter_output_pads()))

    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX = None,
        outpad: PAD_INDEX = None,
        force: bool = None,
    ) -> ffg.Graph:
        """label a filter pad

        :param label: name of the new label. Square brackets are optional.
        :param inpad: input filter pad index or a sequence of pads, defaults to None
        :param outpad: output filter pad index, defaults to None
        :param force: True to delete existing labels, defaults to None
        :return: actual label name

        Only one of inpad and outpad argument must be given.

        If given label already exists, no new label will be created.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        # must convert to FilterGraph as it's the only object with labels
        fg = ffg.Graph([self])
        fg.add_label(label, inpad, outpad, force)
        return fg

    def _input_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """returns True if specified input pad index is available"""

        pos = index[1]
        if pos < 0 or pos >= len(self):
            return False

        # if chained to the previous filter, not avail
        pad_pos = index[2]
        n = self[pos].get_num_inputs()
        return pad_pos >= 0 and pad_pos < (n - 1 if pos else n)

    def _output_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """returns True if specified output pad index is available"""

        pos = index[1]
        nchain = len(self)
        if pos < 0 or pos >= nchain:
            return False

        # if chained to the next filter, not avail
        pad_pos = index[2]
        n = self[pos].get_num_outputs()
        return pad_pos >= 0 and pad_pos < (n - 1 if pos < nchain - 1 else n)

    def _check_partial_pad_index(
        self, index: tuple[int | None, int | None, int | None], is_input: bool
    ) -> bool:
        """True if defined values of the partial pad index are valid"""

        if index[0] is not None and index[0] > 0:
            return False

        filter = index[1]
        if filter is not None:
            if filter < 0 or filter >= len(self):
                return False

        return any(
            f._check_partial_pad_index((None, None, index[2]), is_input) for f in self
        )

    def _input_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified input pad is chainable"""
        if index[0]:
            return False
        try:
            filter = self[index[1]]
        except IndexError:
            return False
        else:
            return filter._input_pad_is_chainable((0, 0, index[2]))

    def _output_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified output pad is chainable"""
        if index[0]:
            return False
        try:
            filter = self[index[1]]
        except IndexError:
            return False
        else:
            return filter._output_pad_is_chainable((0, 0, index[2]))
