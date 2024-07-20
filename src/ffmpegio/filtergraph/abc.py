from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator, Sequence
import re

from .typing import *
from .exceptions import *


__all__ = ["FilterOperations"]


def validate_pad_index(index: PAD_INDEX):
    try:
        assert isinstance(index, tuple)
        assert len(index) in (1, 2, 3)
        assert all(isinstance(i, (int, type(None))) for i in index)
    except AssertionError:
        raise FiltergraphPadNotFoundError(f"{index=} is an invalid pad index.")


def _check_joinable(outpad, inpad):
    n = outpad.get_num_outputs()
    m = inpad.get_num_inputs()
    if not (n and m):
        raise FiltergraphMismatchError(n, m)
    return n == 1 and m == 1


def _is_label(expr):
    return isinstance(expr, str) and re.match(r"\[[^\[\]]+\]$", expr)


class FilterOperations(ABC):

    @abstractmethod
    def get_num_inputs(self) -> int:
        """get the number of input pads of the filter
        :return: number of input pads
        """

    @abstractmethod
    def get_num_outputs(self) -> int:
        """get the number of output pads of the filter
        :return: number of output pads
        """

    def next_input_pad(self, chainable_first: bool) -> PAD_INDEX:
        """get next available input pad

        :param chainable_first: True to retrieve the last pad first, then the rest sequentially
        """
        return next(self.iter_input_pads(chainable_first=chainable_first))[0]

    def next_output_pad(self, chainable_first: bool) -> PAD_INDEX:
        """get next available output pad

        :param chainable_first: True to retrieve the last pad first, then the rest sequentially
        """
        return next(self.iter_output_pads(chainable_first=chainable_first))[0]

    @abstractmethod
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
        """Iterate over input pads of the filter

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last input pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last input first then the rest, defaults to False
        :param include_connected: True to include pads connected to input streams, defaults to False
        :param exclude_named: True to leave out named inputs, defaults to False to return only all inputs
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

    @abstractmethod
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
        """Iterate over output pads of the filter

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last output pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last output first then the rest, defaults to False
        :param include_connected: True to include pads connected to output streams, defaults to False
        :param exclude_named: True to leave out named outputs, defaults to False to return only all inputs
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

    def has_label(
        self,
        label: str,
        *,
        linkable: bool = False,
        input: bool = False,
        output: bool = False,
    ) -> bool:
        """True if filtergraph object has the label

        :param label: link label string
        :param linkable: True to return True only if the label points to unlinked input or output
        :param input: True to return True only if the label is a dangling input label or an input stream spec
        :param output: True to return True only if the label is a dangling output label

        Example:

        fg.has_label('in',linkable=True,input=True) 

        This statement only returns True if there is Link Label 'in' which is associated with an input pad
        of a filter but not connected to any output pad.

        On the other hand,

        fg.has_label('0:v',linkable=True,input=True) 

        will always return False because it is an input stream specifier thus always connected.

        """
        raise FFmpegioError()

    def get_label(
        self,
        is_input: bool = True,
        index: PAD_INDEX | None = None,
        inpad: PAD_INDEX | None = None,
        outpad: PAD_INDEX | None = None,
    ) -> str | None:
        """get label of the specified filter input or output pad

        :param label: _description_
        :param inpad: _description_, defaults to None
        :param outpad: _description_, defaults to None
        :raises ValueError: _description_
        :raises ValueError: _description_
        :raises NotImplementedError: _description_
        :raises ValueError: _description_
        :raises ValueError: _description_
        :raises NotImplementedError: _description_
        :return: _description_
        """

        raise FFmpegioError()

    @abstractmethod
    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX | Sequence[PAD_INDEX] = None,
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

        If inpad indices are given, the label must be an input stream specifier.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

    @abstractmethod
    def resolve_index(self, is_input: bool, index: PAD_INDEX) -> PAD_INDEX:
        """Resolve label or partial pad index to full 3-element pad index

        :param is_input: True if resolving a filter pad
        :param index: (partial) pad index
        :return: a full 3-element pad index
        """

    @abstractmethod
    def __getitem__(self, key): ...

    @abstractmethod
    def __str__(self): ...

    @abstractmethod
    def __repr__(self) -> str: ...

    @abstractmethod
    def __add__(self, other):
        """join"""

    @abstractmethod
    def __radd__(self, other):
        """join"""

    @abstractmethod
    def __mul__(self, __n: int):
        """stack"""

    @abstractmethod
    def __rmul__(self, __n: int):
        """stack"""

    @abstractmethod
    def __or__(self, other):
        """stack"""

    @abstractmethod
    def __ror__(self, other):
        """stack"""

    def __rshift__(self, other) -> Graph:
        """self >> other|label
        self >> (index, other|label)
        self >> (index, other_index, other)
        self >> [other0, other1, ...]"""

        def parse_other(other):
            if isinstance(other, tuple):
                if len(other) > 2:
                    index, other_index, other = other
                else:
                    index, other = other
                    other_index = None

                if index is not None:
                    if isinstance(index, int):
                        index = (index,)
                    validate_pad_index(index)
                if other_index is not None:
                    if isinstance(other_index, int):
                        other_index = (other_index,)
                    validate_pad_index(other_index)
            else:
                index = None
                other_index = None

            # parse if other is a filtergraph expression
            try:
                other = as_filtergraph_object(other)
            except FiltergraphInvalidExpression:
                if _is_label(other):
                    if other_index is not None:
                        raise ValueError("A label cannot have a pad index.")
                    return self.add_label(other, outpad=index)
                else:
                    raise ValueError(
                        f"{other=} is neither a valid filtergraph expression nor a label"
                    )
            except:
                # TODO: screen out ffmpegio errors
                raise NotImplementedError

            return other, index, other_index

        # if output is a list
        if isinstance(other, list):
            # match the pad indices first
            others = [parse_other(o) for o in other]

            # get pad indices assigned by the caller
            assigned_idx = [
                self.resolve_index(False, i) for o, i, oi in others if i is not None
            ]

            it_avail = self.iter_output_pads(chainable_first=False)
            graph = as_filtergraph(self)

            for o, i, oi in others:
                if i is not None:
                    # find the next available pad
                    while i_ := next(it_avail):
                        if i_ not in assigned_idx:
                            i = i_
                # attach the other object to the graph
                graph.attach(o, i, oi or other.next_input_pad(chainable_first=True))

            return graph

        # parse other argument, separate the indices if given
        try:
            other, index, other_index = parse_other(other)
        except NotImplementedError:
            return NotImplemented

        other_is_not_graph = isinstance(other, Graph)

        if index is None and other is None and other_is_not_graph:
            return self._chain_first(other)

        if index is None:
            index = self.next_output_pad(chainable_first=True)
        if other_index is None:
            other_index = other.next_input_pad(chainable_first=True)

        # if not Chain or Graph, use other's >> operator
        return (
            Graph(self).attach(other, index, other_index)
            if other_is_not_graph
            else other.rattach(self, index, other_index)
        )

    def __rrshift__(self, other):
        """other >> self, (other, index) >> self : attach input label or filter"""

        def parse_other(other):
            if isinstance(other, tuple):
                if len(other) > 2:
                    other, other_index, index = other
                else:
                    index, other = other
                    other_index = None

                if index is not None:
                    if isinstance(index, int):
                        index = (index,)
                    validate_pad_index(index)
                if other_index is not None:
                    if isinstance(other_index, int):
                        other_index = (other_index,)
                    validate_pad_index(other_index)
            else:
                index = None
                other_index = None

            # parse if other is a filtergraph expression
            try:
                other = as_filtergraph_object(other)
            except FiltergraphInvalidExpression:
                if _is_label(other):
                    if other_index is not None:
                        raise ValueError("A label cannot have a pad index.")
                    return self.add_label(other, outpad=index)
                else:
                    raise ValueError(
                        f"{other=} is neither a valid filtergraph expression nor a label"
                    )
            except:
                # TODO: screen out ffmpegio errors
                raise NotImplementedError

            return other, index, other_index

        # if output is a list
        if isinstance(other, list):
            # match the pad indices first
            others = [parse_other(o) for o in other]

            # get pad indices assigned by the caller
            assigned_idx = [
                self.resolve_index(False, i) for o, i, oi in others if i is not None
            ]

            it_avail = self.iter_output_pads(chainable_first=False)
            graph = as_filtergraph(self)

            for o, i, oi in others:
                if i is not None:
                    # find the next available pad
                    while i_ := next(it_avail):
                        if i_ not in assigned_idx:
                            i = i_
                # attach the other object to the graph
                graph.attach(o, i, oi or other.next_input_pad(chainable_first=True))

            return graph

        # parse other argument, separate the indices if given
        try:
            other, index, other_index = parse_other(other)
        except NotImplementedError:
            return NotImplemented

        other_is_not_graph = isinstance(other, Graph)

        if index is None and other is None and other_is_not_graph:
            self._rchain(other)

        if other_index is None:
            other_index = other.next_output_pad(chainable_first=True)
        if index is None:
            index = self.next_input_pad(chainable_first=True)

        # if not Chain or Graph, use other's >> operator
        return (
            Graph(self).rattach(other, index, other_index)
            if other_is_not_graph
            else other.attach(self, index, other_index)
        )

    @abstractmethod
    def _chain(
        self, other: Filter | Chain, chain_index: int | None = None
    ) -> Chain | Graph:
        """chain self->other (no var check)

        If self is not a Graph, chain_index is ignored.
        If self is a Graph, chain_index may be used to specify the chain to attach other to.
        If not specified, attaches to the first chain.
        """

    @abstractmethod
    def _rchain(
        self, other: Filter | Chain, chain_index: int | None = None
    ) -> Chain | Graph:
        """chain other->self (no var check)

        If self is not a Graph, chain_index is ignored.
        If self is a Graph, chain_index may be used to specify the chain to attach other to.
        If not specified, attaches to the first chain.
        """
