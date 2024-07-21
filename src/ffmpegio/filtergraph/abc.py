from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator, Sequence
import re

from .typing import *
from .exceptions import *
from ._convert import as_filtergraph_object, as_filtergraph, as_filterchain

from .Graph import Graph  # circular
from .Filter import Filter  # circular
from .Chain import Chain  # circular

__all__ = ["FilterGraphObject"]


def _check_joinable(outpad, inpad):
    n = outpad.get_num_outputs()
    m = inpad.get_num_inputs()
    if not (n and m):
        raise FiltergraphMismatchError(n, m)
    return n == 1 and m == 1


def _is_label(expr):
    return isinstance(expr, str) and re.match(r"\[[^\[\]]+\]$", expr)


class FilterGraphObject(ABC):

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

    def next_input_pad(
        self, pad=None, filter=None, chain=None, chainable_first: bool = False
    ) -> PAD_INDEX:
        """get next available input pad

        :param chainable_first: True to retrieve the last pad first, then the rest sequentially
        """
        return next(
            self.iter_input_pads(pad, filter, chain, chainable_first=chainable_first)
        )[0]

    def next_output_pad(
        self, pad=None, filter=None, chain=None, chainable_first: bool = False
    ) -> PAD_INDEX:
        """get next available output pad

        :param chainable_first: True to retrieve the last pad first, then the rest sequentially
        """
        return next(
            self.iter_output_pads(pad, filter, chain, chainable_first=chainable_first)
        )[0]

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

    # Label management methods (default operation for non-Graph objects)

    def iter_input_labels(
        self, exclude_stream_specs: bool = False
    ) -> Generator[tuple[str, PAD_INDEX]]:
        """iterate over the dangling labeled input pads of the filtergraph object

        :param exclude_stream_specs: True to not include input streams
        :yield: a tuple of 3-tuple pad index and the pad index of the connected output pad if connected
        """

        raise StopIteration()

    def iter_output_labels(self) -> Generator[tuple[str, PAD_INDEX]]:
        """iterate over the dangling labeled output pads of the filtergraph object

        :yield: a tuple of 3-tuple pad index and the pad index of the connected input pad if connected
        """

        raise StopIteration()

    def get_label(
        self,
        input: bool = True,
        index: PAD_INDEX | None = None,
        inpad: PAD_INDEX | None = None,
        outpad: PAD_INDEX | None = None,
    ) -> str | None:
        """get the label string of the specified filter input or output pad

        :param input: True to get label of input pad, False to get label of output pad, defaults to True
        :param index: 3-element tuple to specify the (chain, filter, pad) indices, defaults to None
        :param inpad: alternate argument to specify an input pad index, defaults to None
        :param outpad: alternate argument to specify an output pad index, defaults to None
        :return: the label of the specified pad or ``None`` if no label is assigned.

        If the pad index is invalid, the method raises ``FiltergraphInvalidIndex``.

        """

        if (index is not None) + (inpad is not None) + (outpad is not None) != 1:
            raise ValueError(
                "One and only one of index, inpad, or outpad must be specified."
            )

        if inpad is not None:

            self._get_label()

        return None

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
    def __getitem__(self, key): ...

    @abstractmethod
    def __str__(self): ...

    @abstractmethod
    def __repr__(self) -> str: ...

    # Filtergraph math operators

    @abstractmethod
    def __add__(self, other: FilterGraphObject | str) -> Chain | Graph:
        """join"""

    @abstractmethod
    def __radd__(self, other: FilterGraphObject | str) -> Chain | Graph:
        """join"""

    @abstractmethod
    def __mul__(self, __n: int) -> Graph:
        """duplicate-n-stack"""

    def __rmul__(self, __n: int) -> Graph:
        """duplicate-n-stack"""
        return self.__mul__(__n)

    @abstractmethod
    def __or__(self, other: FilterGraphObject | str) -> Graph:
        """stack"""

    def __ror__(self, other: FilterGraphObject | str) -> Graph:
        """stack"""
        try:
            return as_filtergraph_object(other).__or__(self)
        except FiltergraphInvalidExpression:
            raise
        except:
            NotImplemented

    def __rshift__(
        self,
        other: (
            FilterGraphObject
            | str
            | tuple[FilterGraphObject, PAD_INDEX | str]
            | tuple[FilterGraphObject, PAD_INDEX | str, PAD_INDEX | str]
            | list[
                FilterGraphObject
                | str
                | tuple[FilterGraphObject, PAD_INDEX | str]
                | tuple[FilterGraphObject, PAD_INDEX | str, PAD_INDEX | str]
            ]
        ),
    ) -> Graph:
        """make one-to-one connections

        self >> other|label
        self >> (index, other|label)
        self >> (index, other_index, other)
        self >> [other0, other1, ...]

        If pad is unspecified (i.e., ``index`` is ``None`` or the last
        element of ``index`` is ``None``), chain connection is sought first
        unless multiple other connection points are given.
        """

        def parse_other(other, resolve_omitted=False, chainable_first=True):
            if isinstance(other, tuple):
                if len(other) > 2:
                    index, other_index, other = other
                else:
                    index, other = other
                    other_index = None

            else:
                index = None
                other_index = None

            # parse if other is a filtergraph expression
            try:
                other: FilterGraphObject = as_filtergraph_object(other)
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

            index = self._resolve_pad_index(
                index,
                is_input=False,
                chain_index_omittable=True,
                filter_index_omittable=True,
                pad_index_omittable=True,
                resolve_omitted=resolve_omitted,
                chainable_first=chainable_first,
            )

            other_index = other._resolve_pad_index(
                other_index,
                is_input=True,
                chain_index_omittable=True,
                filter_index_omittable=True,
                pad_index_omittable=True,
                resolve_omitted=False,
                resolve_omitted=resolve_omitted,
                chainable_first=chainable_first,
            )

            return other, index, other_index

        # if output is a list
        if isinstance(other, list):
            # match the pad indices first
            others, indices, other_indices = zip(*(parse_other(o) for o in other))

            # indices ranking
            # - int, int, int    = 3*6 = 18
            # - int, int, None   = 2*5 = 10
            # - int, None, int   = 2*4 = 8
            # - None, int, int   = 2*3 = 6
            # - int, None, None  = 1*3 = 3
            # - None, int, None  = 1*2 = 2
            # - None, None, int  = 1*1 = 1
            # - None, None, None = 0*0 = 0

            def resolve_indices(indices, it_avail, fg_desc, io_desc):
                index_scores = [
                    sum(i is not None for i in index)
                    * sum((3 - j) for j, i in enumerate(index) if i is not None)
                    for index in indices
                ]
                index_assign_order = sorted(
                    range(len(index_scores)), key=index_scores.__getitem__, reverse=True
                )
                try:
                    for i in index_assign_order:
                        if index_scores[i] < 18:
                            indices[i] = next(it_avail)
                except StopIteration:
                    raise FiltergraphPadNotFoundError(
                        f"{fg_desc} does not have enough unconnected {io_desc} pads to complete this operation"
                    )

            resolve_indices(
                indices,
                self.iter_output_pads(chainable_first=False),
                "Filtergraph",
                "input",
            )
            resolve_indices(
                other_indices,
                other.iter_input_pads(chainable_first=False),
                "The other filtergraph",
                "output",
            )

            graph = as_filtergraph(self)

            for o, i, oi in zip(others, indices, other_indices):
                # attach the other object to the graph
                graph.attach(o, i, oi or other.next_input_pad(chainable_first=True))

            return graph

        # parse other argument, separate the indices if given
        try:
            other, index, other_index = parse_other(
                other, resolve_omitted=True, chainable_first=True
            )
        except NotImplementedError:
            return NotImplemented

        if self._output_pad_is_chainable(index) and other._input_pad_is_chainable(
            other_index
        ):
            return self._chain(other, index[0], other_index[0])

        # if not Chain or Graph, use other's >> operator
        return (
            Graph(self).attach(other, index, other_index)
            if isinstance(other, Graph)
            else other.rattach(self, other_index, index)
        )

    def __rrshift__(
        self,
        other: (
            FilterGraphObject
            | str
            | tuple[PAD_INDEX | str, FilterGraphObject]
            | tuple[PAD_INDEX | str, PAD_INDEX | str, FilterGraphObject]
            | list[
                FilterGraphObject
                | str
                | tuple[PAD_INDEX | str, FilterGraphObject]
                | tuple[PAD_INDEX | str, PAD_INDEX | str, FilterGraphObject]
            ]
        ),
    ) -> Graph:
        """make one-to-one connections
        other|label >> self
        (other|label, index) >> self
        (other, other_index, index) >> self
        [other0, other1, ...] >> self

        If pad is unspecified (i.e., ``index`` is ``None`` or the last
        element of ``index`` is ``None``), chain connection is sought first
        unless multiple other connection points are given.
        """

        def parse_other(other, resolve_omitted=False, chainable_first=True):
            if isinstance(other, tuple):
                if len(other) > 2:
                    other, other_index, index = other
                else:
                    other, index = other
                    other_index = None

            else:
                index = None
                other_index = None

            # parse if other is a filtergraph expression
            try:
                other: FilterGraphObject = as_filtergraph_object(other)
            except FiltergraphInvalidExpression:
                if _is_label(other):
                    if other_index is not None:
                        raise ValueError("A label cannot have a pad index.")
                    return self.add_label(other, inpad=index)
                else:
                    raise ValueError(
                        f"{other=} is neither a valid filtergraph expression nor a label"
                    )
            except:
                # TODO: screen out ffmpegio errors
                raise NotImplementedError

            index = self._resolve_pad_index(
                index,
                is_input=True,
                chain_index_omittable=True,
                filter_index_omittable=True,
                pad_index_omittable=True,
                resolve_omitted=resolve_omitted,
                chainable_first=chainable_first,
            )

            other_index = other._resolve_pad_index(
                other_index,
                is_input=False,
                chain_index_omittable=True,
                filter_index_omittable=True,
                pad_index_omittable=True,
                resolve_omitted=False,
                resolve_omitted=resolve_omitted,
                chainable_first=chainable_first,
            )

            return other, index, other_index

        # if output is a list
        if isinstance(other, list):
            # match the pad indices first
            others, indices, other_indices = zip(*(parse_other(o) for o in other))

            # indices ranking
            # - int, int, int    = 3*6 = 18
            # - int, int, None   = 2*5 = 10
            # - int, None, int   = 2*4 = 8
            # - None, int, int   = 2*3 = 6
            # - int, None, None  = 1*3 = 3
            # - None, int, None  = 1*2 = 2
            # - None, None, int  = 1*1 = 1
            # - None, None, None = 0*0 = 0

            def resolve_indices(indices, it_avail, fg_desc, io_desc):
                index_scores = [
                    sum(i is not None for i in index)
                    * sum((3 - j) for j, i in enumerate(index) if i is not None)
                    for index in indices
                ]
                index_assign_order = sorted(
                    range(len(index_scores)), key=index_scores.__getitem__, reverse=True
                )
                try:
                    for i in index_assign_order:
                        if index_scores[i] < 18:
                            indices[i] = next(it_avail)
                except StopIteration:
                    raise FiltergraphPadNotFoundError(
                        f"{fg_desc} does not have enough unconnected {io_desc} pads to complete this operation"
                    )

            resolve_indices(
                indices,
                self.iter_input_pads(chainable_first=False),
                "Filtergraph",
                "output",
            )
            resolve_indices(
                other_indices,
                other.iter_output_pads(chainable_first=False),
                "The other filtergraph",
                "input",
            )

            graph = as_filtergraph(self)

            for o, i, oi in zip(others, indices, other_indices):
                # attach the other object to the graph
                graph.rattach(o, i, oi or other.next_input_pad(chainable_first=True))

            return graph

        # parse other argument, separate the indices if given
        try:
            other, index, other_index = parse_other(
                other, resolve_omitted=True, chainable_first=True
            )
        except NotImplementedError:
            return NotImplemented

        if self._input_pad_is_chainable(index) and other._output_pad_is_chainable(
            other_index
        ):
            return other._chain(self, other_index[0], index[0])

        # if not Chain or Graph, use other's >> operator
        return (
            Graph(self).rattach(other, index, other_index)
            if isinstance(other, Graph)
            else other.attach(self, other_index, index)
        )

    @abstractmethod
    def _chain(
        self, other: FilterGraphObject, chain_index: int, other_chain_index: int
    ) -> Chain | Graph:
        """chain self->other (no var check)

        :param other: the other filitergraph object to chain to
        :param chain_index: chain id of self, nonzero only if self is a ``Graph``
        :param other_chain_index: chain of other, nonzero only if other is a ``Graph``
        :return: ``Graph`` object if either self or other is a ``Graph`` else ``Chain``
        """

    def _rchain(
        self, other: FilterGraphObject, chain_id: int, other_chain_id: int
    ) -> Chain | Graph:
        """chain other->self (no var check)

        :param other: the other filitergraph object to chain to
        :param chain_index: chain id of self, nonzero only if self is a ``Graph``
        :param other_chain_index: chain of other, nonzero only if other is a ``Graph``
        :return: ``Graph`` object if either self or other is a ``Graph`` else ``Chain``
        """

    def _resolve_pad_index(
        self,
        index_or_label: PAD_INDEX | str | None,
        *,
        is_input: bool = True,
        chain_index_omittable: bool = False,
        filter_index_omittable: bool = False,
        pad_index_omittable: bool = False,
        resolve_omitted: bool = True,
        chain_fill_value: int | None = None,
        filter_fill_value: int | None = None,
        pad_fill_value: int | None = None,
        chainable_first: bool = False,
    ) -> PAD_INDEX:
        """Resolve unconnected label or pad index to full 3-element pad index

        :param index_or_label: pad index set or pad label or ``None`` to auto-select
        :param is_input: True to resolve an input pad, else an output pad, defaults to True
        :param chain_index_omittable: True to allow ``None`` chain index, defaults to False
        :param filter_index_omittable: True to allow ``None`` filter index, defaults to False
        :param pad_index_omittable: True to allow ``None`` pad index, defaults to False
        :param resolve_omitted: True to fill each omitted value with the prescribed fill value.
        :param chain_fill_value: if ``chain_index_omittable=True`` and chain index is either not
                                 given or ``None``, this value will be returned, defaults to None,
                                 which returns the first available pad.
        :param filter_fill_value:if ``filter_index_omittable=True`` and filter index is either not
                                 given or ``None``, this value will be returned, defaults to None,
                                 which returns the first available pad.
        :param pad_fill_value: if ``pad_index_omittable=True`` and either ``index`` is None or
                               pad index is ``None``, this value will be returned, defaults to None,
                               which returns the first available pad.
        :param chainable_first: if True, chainable pad is selected first, defaults to False

        One and only one of ``index`` and ``label`` must be specified. If the given index
        or label is invalid, it raises FiltergraphPadNotFoundError.
        """

        # base implementation - guarantees to return 3-element tuple index WITHOUT converting None fill_values

        pad_type = "input" if is_input else "output"

        if index_or_label is None:  # all undefined
            if chain_index_omittable and filter_index_omittable and pad_index_omittable:
                return (chain_fill_value, filter_fill_value, pad_fill_value)
            else:
                raise ValueError(
                    "Either index or label must be specified (partial index not allowed)."
                )

        elif isinstance(index_or_label, str):  # label given

            try:
                if is_input:
                    index = next(
                        index
                        for label, index in self.iter_input_labels(
                            index_or_label, exclude_stream_specs=True
                        )
                        if label == index
                    )
                else:
                    index = next(
                        index
                        for label, index in self.iter_output_labels(index_or_label)
                        if label == index
                    )

            except StopIteration:
                raise FiltergraphPadNotFoundError(
                    f"{index_or_label=} is not defined on the filtergraph."
                )
            return index

        else:  # index given

            if isinstance(index_or_label, int):
                # only pad index given
                if chain_index_omittable and filter_index_omittable:
                    return (
                        chain_fill_value,
                        filter_fill_value,
                        pad_fill_value if index is None else index,
                    )

            allow_partial_index = (
                chain_index_omittable or filter_index_omittable or pad_index_omittable
            )

            min_len = (
                3
                if not chain_index_omittable
                else 2 if not filter_index_omittable else 1
            )
            index_types = (int, type(None)) if allow_partial_index else int

            if not (
                isinstance(index_or_label, tuple)
                and len(index_or_label) in range(min_len, 4)
                and all(isinstance(i, index_types) for i in index_or_label)
            ):
                raise FiltergraphPadNotFoundError(
                    f"{index_or_label=} is an invalid {pad_type} pad index."
                )

            def get_value(i, omittable, fill_value):
                try:
                    value = index_or_label[i]
                except IndexError:
                    value = fill_value
                else:
                    if omittable and value is None:
                        value = fill_value
                return value

            index = (
                get_value(-3, chain_index_omittable, chain_fill_value),
                get_value(-2, filter_index_omittable, filter_fill_value),
                get_value(-1, pad_index_omittable, pad_fill_value),
            )

            if allow_partial_index and any(i is None for i in index):
                if resolve_omitted:
                    iter_pads = (
                        self.iter_input_pads if is_input else self.iter_output_pads
                    )
                    try:
                        index = next(iter_pads(chainable_first=chainable_first))
                    except StopIteration:
                        raise FiltergraphPadNotFoundError(
                            f"{index_or_label=} could not be resolve to an unused {pad_type} pad index."
                        )
                elif not self._check_partial_pad_index(index, is_input=is_input):
                    raise FiltergraphPadNotFoundError(
                        f"{index_or_label=} cannot be resolve to a valid {pad_type} pad index."
                    )
                return index
            else:
                # validate
                if (
                    self._input_pad_is_available
                    if is_input
                    else self._output_pad_is_available
                )(index):
                    return index
                else:
                    raise FiltergraphPadNotFoundError(
                        f"{index_or_label=} is either already connected or invalid {pad_type} pad."
                    )

    @abstractmethod
    def _input_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """index must be 3-element tuple"""

    @abstractmethod
    def _output_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        """index must be 3-element tuple"""

    @abstractmethod
    def _check_partial_pad_index(
        self, index: tuple[int | None, int | None, int | None], is_input: bool
    ) -> bool:
        """True if defined values of the partial pad index are valid"""

    @abstractmethod
    def _input_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified input pad is chainable"""

    @abstractmethod
    def _output_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified output pad is chainable"""
