from __future__ import annotations

from collections import UserList
from collections.abc import Callable, Generator
from functools import reduce


from .typing import *
from .exceptions import *
from .abc import FilterOperations

from ..utils import filter as filter_utils

__all__ = ["Chain"]


class Chain(UserList, FilterOperations):
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
        elif isinstance(filter_specs, Filter):
            filter_specs = [filter_specs]

        super().__init__(
            () if filter_specs is None else (as_filter(fspec) for fspec in filter_specs)
        )

    def resolve_index(self, is_input: bool, index: PAD_INDEX | str) -> PAD_INDEX:
        try:
            # cannot be str
            validate_pad_index(index)

            # chain index (if given) must be 0
            assert all(i in (0, None) for i in index[:-2])

            # get pad index
            i = index[-1]

            # get filter index
            try:
                j = index[-2]
            except:
                j = None

            return next(
                (self.iter_input_pads if is_input else self.iter_output_pads)(
                    filter=j, pad=i
                )
            )[0]

        except:
            raise FiltergraphPadNotFoundError("input" if is_input else "output", index)

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
        super().__setitem__(key, as_filter(value))

    def append(self, item):
        return super().append(as_filter(item))

    def extend(self, other):
        return super().extend([as_filter(f) for f in other])

    def insert(self, i, item):
        return super().insert(i, as_filter(item))

    def __contains__(self, item):
        item = as_filter(item)
        return any((f.name == item for f in self.data))

    def __mul__(self, __n):
        res = super().__mul__(__n)
        _check_joinable(self, self)
        return res

    def __rmul__(self, __n):
        return self.__mul__(__n)

    def __add__(self, other):
        # chain
        try:
            other = as_filterchain(other)
        except Exception:
            return NotImplemented
        n = len(self)
        if n and len(other):
            if _check_joinable(self, other):
                return Chain([*self, *other])
            else:
                return Graph([self]).join(other)
        return self if n else other

    def __radd__(self, other):
        # form a filterchain/filtergraph by appending this to other filter
        try:
            other = as_filterchain(other)
        except Exception:
            return NotImplemented

        n = len(self)
        if n and len(other):
            if _check_joinable(other, self):
                return Chain([*other, *self])
            else:
                return Graph([other]).join(self)
        return self if n else other

    def __mul__(self, __n):
        if len(self):
            return Graph([self] * __n) if isinstance(__n, int) else NotImplemented
        else:
            return Chain(self)

    def __rmul__(self, __n):
        if len(self):
            return Graph([self] * __n) if isinstance(__n, int) else NotImplemented
        else:
            return Chain(self)

    def __or__(self, other):
        # create filtergraph with self and other as parallel chains, self first

        try:
            other = as_filterchain(other)
        except:
            return NotImplemented

        n = len(self)
        m = len(other)
        return Graph([self, other]) if n and m else self if n else other

    def __ror__(self, other):
        # create filtergraph with self and other as parallel chains, self last

        try:
            other = as_filterchain(other)
        except:
            return NotImplemented

        n = len(self)
        m = len(other)
        return Graph([other, self]) if n and m else self if n else other

    def _chain(
        self, other: Filter | Chain, chain_index: int | None = None
    ) -> Chain | Graph:
        """chain self->other (no input check)

        If self is not a Graph, chain_index is ignored.
        If self is a Graph, chain_index may be used to specify the chain to attach other to.
        If not specified, attaches to the first chain.
        """
        return Chain([*self, other] if isinstance(other, Filter) else [*self, *other])

    def _rchain(
        self, other: Filter | Chain, chain_index: int | None = None
    ) -> Chain | Graph:
        """chain other->self (no input check)

        If self is not a Graph, chain_index is ignored.
        If self is a Graph, chain_index may be used to specify the chain to attach other to.
        If not specified, attaches to the first chain.
        """
        return Chain([other, *self] if isinstance(other, Filter) else [*other, *self])

    def __mul__(self, __n):
        if not isinstance(__n, int):
            return NotImplemented
        if not len(self.data):
            return Chain(self)
        fg = Graph([self])
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
        filters: list[Filter],
        iter_filter_pad: Callable,
        i_first: int,
        i_nochain: int,
        pad: int | None,
        chain: Literal[0] | None,
        exclude_chainable: bool,
        chainable_first: bool,
        include_connected: bool,
    ) -> Generator[tuple[PAD_INDEX, Filter, PAD_INDEX | None]]:
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
    ) -> Generator[tuple[PAD_INDEX, Filter, PAD_INDEX | None]]:
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
            Filter.iter_input_pads,
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
    ) -> Generator[tuple[PAD_INDEX, Filter, PAD_INDEX | None]]:
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
            Filter.iter_output_pads,
            i_first,
            len(self.data) - 1,
            pad,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
        ):
            yield v

    def get_chainable_input_pad(self) -> tuple[PAD_INDEX, Filter] | None:
        """get first filter's input pad, which can be chained

        :return: filter position, input pad poisition, and filter object.
                 If the head filter is a source filter, returns None.
        """

        if not len(self):
            return None
        f = self[-1]
        nin = f.get_num_inputs()
        return ((0, nin - 1), f) if nin else None

    def get_chainable_output_pad(self) -> tuple[PAD_INDEX, Filter] | None:
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

    def validate_input_index(self, pos, pad_pos):

        if pos < 0 or pos >= len(self):
            raise Chain.Error(f"invliad filter position #{pos}.")

        # if chained to the previous filter, not avail
        n = self[pos].get_num_inputs()
        if pad_pos < 0 or pad_pos >= (n - 1 if pos else n):
            raise Chain.Error(f"invliad input pad position #{pos} for {self[pos]}.")

    def validate_output_index(self, pos, pad_pos):

        if pos < 0 or pos >= len(self):
            raise Chain.Error(f"invliad filter position #{pos}.")

        # if chained to the next filter, not avail
        n = self[pos].get_num_outputs()
        if pad_pos < 0 or pad_pos >= (n - 1 if pos < len(self.data) - 1 else n):
            raise Chain.Error(f"invliad output pad position #{pos} for {self[pos]}.")

    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX = None,
        outpad: PAD_INDEX = None,
        force: bool = None,
    ) -> Graph:
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
        fg = Graph([self])
        fg.add_label(label, inpad, outpad, force)
        return fg
