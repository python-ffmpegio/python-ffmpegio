from __future__ import annotations

from typing import Literal
from abc import ABC, abstractmethod
from collections.abc import Generator, Sequence
import re

from .typing import PAD_INDEX
from .exceptions import *

from .. import filtergraph as fgb

__all__ = ["FilterGraphObject"]


def _is_label(expr):
    return isinstance(expr, str) and re.match(r"\[[^\[\]]+\]$", expr)


class FilterGraphObject(ABC):

    def get_num_pads(self, input: bool) -> int:
        """get the number of available pads at input or output

        :param input: True to get the input count, False for the output count.
        """
        return self.get_num_inputs() if input else self.get_num_outputs()

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

    def get_num_chains(self) -> int:
        """get the number of chains"""
        return 1

    @abstractmethod
    def get_num_filters(self, chain: int) -> int:
        """get the number of filters of the specfied chain

        :param chain: id of the chain
        """

    def next_input_pad(
        self,
        pad=None,
        filter=None,
        chain=None,
        chainable_first: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
    ) -> PAD_INDEX:
        """get next available input pad

        :param chainable_first: True to retrieve the last pad first, then the rest sequentially
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all inputs
        """
        return next(
            self.iter_input_pads(
                pad,
                filter,
                chain,
                chainable_first=chainable_first,
                unlabeled_only=unlabeled_only,
                chainable_only=chainable_only,
            )
        )[0]

    def next_output_pad(
        self,
        pad=None,
        filter=None,
        chain=None,
        chainable_first: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
    ) -> PAD_INDEX:
        """get next available output pad

        :param chainable_first: True to retrieve the last pad first, then the rest sequentially
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all inputs
        """
        return next(
            self.iter_output_pads(
                pad,
                filter,
                chain,
                chainable_first=chainable_first,
                unlabeled_only=unlabeled_only,
                chainable_only=chainable_only,
            )
        )[0]

    @abstractmethod
    def iter_chains(
        self,
        skip_if_no_input: bool = False,
        skip_if_no_output: bool = False,
        chainable_only: bool = False,
    ) -> Generator[tuple[int, fgb.Chain]]:
        """iterate over chains of the filtergraphobject

        :param skip_if_no_input: True to skip chains without available input pads, defaults to False
        :param skip_if_no_output: True to skip chains without available output pads, defaults to False
        :param chainable_only: True to further restrict ``skip_if_no_input`` and ``skip_if_no_input``
                               arguments to require chainable input or output, defaults to False to
                               allow any input/output
        :yield: chain id and chain object
        """

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
        unlabeled_only: bool = False,
        chainable_only: bool = False,
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter]]:
        """Iterate over input pads of the filter

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last input pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last input first then the rest, defaults to False
        :param include_connected: True to include pads connected to input streams, defaults to False
        :param unlabeled_only: True to leave out named inputs, defaults to False to return all inputs
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all inputs
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
        unlabeled_only: bool = False,
        chainable_only: bool = False,
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter, PAD_INDEX | None]]:
        """Iterate over output pads of the filter

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last output pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last output first then the rest, defaults to False
        :param include_connected: True to include pads connected to output streams, defaults to False
        :param unlabeled_only: True to leave out named outputs, defaults to False to return all outputs
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all outputs
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

        if index is not None:
            return self._get_label(input, index)
        if inpad is not None:
            return self._get_label(True, inpad)
        if (outpad is not None) != 1:
            return self._get_label(False, outpad)
        raise ValueError(
            "One and only one of index, inpad, or outpad must be specified."
        )

    def _get_label(self, input: bool, index: PAD_INDEX):
        return None

    def get_input_pad(
        self, index_or_label: PAD_INDEX | str
    ) -> tuple[PAD_INDEX, str | None]:
        """resolve (unconnected) input pad from pad index or label

        :param index: pad index or link label
        :return: filter input pad index and its link label (None if not assigned)

        Raises error if specified label does not resolve uniquely to an input pad
        """

        index = self._resolve_pad_index(index_or_label, is_input=True)
        return index, self._get_label(True, index)

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
        return index, self._get_label(False, index)

    @abstractmethod
    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX | Sequence[PAD_INDEX] = None,
        outpad: PAD_INDEX = None,
        force: bool = None,
    ) -> fgb.Graph:
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
    def _connect(
        self,
        right: fgb.abc.FilterGraphObject,
        links: list[tuple[PAD_INDEX, PAD_INDEX]],
        chain_siso: bool = True,
        replace_sws_flags: bool | None = None,
    ) -> fgb.Graph:
        """stack another Graph and make connection from self to the other

        :param right: other filtergraph
        :param links: a list of tuples, pairing self's output pad and right's ipnut pad
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :param replace_sws_flags: True to use `right` sws_flags if present,
                                  False to drop `right` sws_flags,
                                  None to throw an exception (default)
        :return: new filtergraph object

        * link labels may be auto-renamed if there is a conflict

        """

    @abstractmethod
    def _rconnect(
        self,
        left: fgb.abc.FilterGraphObject,
        links: list[tuple[PAD_INDEX, PAD_INDEX]],
        chain_siso: bool = True,
        replace_sws_flags: bool | None = None,
    ) -> fgb.Graph:
        """stack another Graph and make connection from the other to self

        :param right: other filtergraph
        :param links: a list of tuples, pairing left's output pad and self's ipnut pad
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :param replace_sws_flags: True to use `right` sws_flags if present,
                                  False to drop `right` sws_flags,
                                  None to throw an exception (default)
        :return: new filtergraph object

        * link labels may be auto-renamed if there is a conflict

        """

    def connect(
        self,
        right: fgb.abc.FilterGraphObject | str,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
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

    def rconnect(
        self,
        left: fgb.abc.FilterGraphObject | str,
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

    def join(
        self,
        right: fgb.abc.FilterGraphObject | str,
        how: Literal["chainable", "per_chain", "all", "auto"] = "per_chain",
        match_scalar: bool = False,
        ignore_labels: bool = False,
        chain_siso: bool = True,
        replace_sws_flags: bool = None,
    ) -> fgb.Graph | None:
        """append another Graph object and auto-connect its inputs to the outputs of this filtergraph

        :param right: right filtergraph to be appended
        :param how: method on how to mate input and output, defaults to "per_chain".

            ===========  ===================================================================
            'chainable'  joins only chainable input pads and output pads.
            'per_chain'  joins one pair of first available input pad and output pad of each
                         mating chains. Source and sink chains are ignored.
            'all'        joins all input pads and output pads
            'auto'       tries 'per_chain' first, if fails, then tries 'all'.
            ===========  ===================================================================

        :param match_scalar: True to multiply self if SO-MI connection or right if MO-SI connection
                              to single-ended entity to the other, defaults to False
        :param ignore_labels: True to pair pads w/out checking pad labels, default: True
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :param replace_sws_flags: True to use other's sws_flags if present,
                                  False to ignore other's sws_flags,
                                  None to throw an exception (default)
        :return: Graph with the appended filter chains or None if inplace=True.
        """

    def rjoin(
        self,
        left: fgb.abc.FilterGraphObject | str,
        how: Literal["chainable", "per_chain", "all", "auto"] = "per_chain",
        match_scalar: bool = False,
        ignore_labels: bool = False,
        chain_siso: bool = True,
        replace_sws_flags: bool = None,
    ) -> fgb.Graph | None:
        """append another Graph object and connect all inputs to the outputs of this filtergraph

        :param right: right filtergraph to be appended
        :param how: method on how to mate input and output, defaults to "per_chain".

            ===========  ===================================================================
            'chainable'  joins only chainable input pads and output pads.
            'per_chain'  joins one pair of first available input pad and output pad of each
                         mating chains. Source and sink chains are ignored.
            'all'        joins all input pads and output pads
            'auto'       tries 'per_chain' first, if fails, then tries 'all'.
            ===========  ===================================================================

        :param match_scalar: True to multiply self if SO-MI connection or right if MO-SI connection
                              to single-ended entity to the other, defaults to False
        :param ignore_labels: True to pair pads w/out checking pad labels, default: True
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :param replace_sws_flags: True to use other's sws_flags if present,
                                  False to ignore other's sws_flags,
                                  None to throw an exception (default)
        :return: Graph with the appended filter chains or None if inplace=True.
        """

    def attach(
        self,
        right: fgb.abc.FilterGraphObject | str,
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

    @abstractmethod
    def __getitem__(self, key): ...

    @abstractmethod
    def __str__(self): ...

    @abstractmethod
    def __repr__(self) -> str: ...

    # Filtergraph math operators

    @abstractmethod
    def __add__(self, other: FilterGraphObject | str) -> fgb.Chain | fgb.Graph:
        """join"""

    @abstractmethod
    def __radd__(self, other: FilterGraphObject | str) -> fgb.Chain | fgb.Graph:
        """join"""

    @abstractmethod
    def __mul__(self, __n: int) -> fgb.Graph:
        """duplicate-n-stack"""

    def __rmul__(self, __n: int) -> fgb.Graph:
        """duplicate-n-stack"""
        return self.__mul__(__n)

    @abstractmethod
    def __or__(self, other: FilterGraphObject | str) -> fgb.Graph:
        """stack"""

    def __ror__(self, other: FilterGraphObject | str) -> fgb.Graph:
        """stack"""
        try:
            return fgb.as_filtergraph_object(other).__or__(self)
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
    ) -> fgb.Graph:
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
                other: FilterGraphObject = fgb.as_filtergraph_object(other)
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
                chain_id_omittable=True,
                filter_id_omittable=True,
                pad_id_omittable=True,
                resolve_omitted=resolve_omitted,
                chainable_first=chainable_first,
            )

            other_index = other._resolve_pad_index(
                other_index,
                is_input=True,
                chain_id_omittable=True,
                filter_id_omittable=True,
                pad_id_omittable=True,
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

            indices = resolve_indices(
                indices,
                self.iter_output_pads(chainable_first=False),
                "Filtergraph",
                "input",
            )
            other_indices = resolve_indices(
                other_indices,
                other.iter_input_pads(chainable_first=False),
                "The other filtergraph",
                "output",
            )

            graph = fgb.as_filtergraph(self)

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

        # if not Chain or Graph, use other's >> operator
        return (
            self._chain(other, index[0], other_index[0])
            if self._output_pad_is_chainable(index)
            and other._input_pad_is_chainable(other_index)
            else self._attach(True, other, index, other_index)
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
    ) -> fgb.Graph:
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
                other: FilterGraphObject = fgb.as_filtergraph_object(other)
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
                chain_id_omittable=True,
                filter_id_omittable=True,
                pad_id_omittable=True,
                resolve_omitted=resolve_omitted,
                chainable_first=chainable_first,
            )

            other_index = other._resolve_pad_index(
                other_index,
                is_input=False,
                chain_id_omittable=True,
                filter_id_omittable=True,
                pad_id_omittable=True,
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

            graph = self

            for o, i, oi in zip(others, indices, other_indices):
                # attach the other object to the graph
                graph = graph._attach(
                    False, o, i, oi or other.next_input_pad(chainable_first=True)
                )

            return graph

        # parse other argument, separate the indices if given
        try:
            other, index, other_index = parse_other(
                other, resolve_omitted=True, chainable_first=True
            )
        except NotImplementedError:
            return NotImplemented

        return (
            self._chain(False, other, index[0], other_index[0])
            if self._output_pad_is_chainable(index)
            and other._input_pad_is_chainable(other_index)
            else self._attach(False, other, index, other_index)
        )

    @abstractmethod
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
        chainable_only: bool = False,
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
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all pads

        One and only one of ``index`` and ``label`` must be specified. If the given index
        or label is invalid, it raises FiltergraphPadNotFoundError.
        """

        # base implementation - guarantees to return 3-element tuple index WITHOUT converting None fill_values

        # label, if allowed, must be resolved in the subclass
        if isinstance(index_or_label, str):
            raise FiltergraphPadNotFoundError(
                f"{index_or_label=} is not defined on the filtergraph."
            )

        # put missing or pad-only input to a 3-element tuple format
        index = (
            (None, None, None)
            if index_or_label is None
            else (
                (None, None, index_or_label)
                if isinstance(index_or_label, int)
                else (
                    index_or_label
                    if len(index_or_label) == 3
                    else (*((None,) * (3 - len(index_or_label))), *index_or_label)
                )
            )
        )

        allow_partial_index = (
            chain_id_omittable or filter_id_omittable or pad_id_omittable
        )

        index_types = (int, type(None)) if allow_partial_index else int

        pad_type = "input" if is_input else "output"  # for error messages

        if not (all(isinstance(i, index_types) for i in index)):
            raise FiltergraphPadNotFoundError(
                f"{index_or_label=} is an invalid {pad_type} pad index."
            )

        def get_value(id_type, id_value, omittable, fill_value):
            if id_value is None and not omittable:
                raise FiltergraphPadNotFoundError(f"{id_type} id must be specified.")
            return fill_value if id_value is None else id_value

        index = tuple(
            get_value(id_type, id, omittable, fill_value)
            for id_type, id, omittable, fill_value in zip(
                ("chain", "filter", "pad"),
                index,
                (chain_id_omittable, filter_id_omittable, pad_id_omittable),
                (chain_fill_value, filter_fill_value, pad_fill_value),
            )
        )

        if allow_partial_index and any(i is None for i in index):
            if resolve_omitted:
                iter_pads = self.iter_input_pads if is_input else self.iter_output_pads
                try:
                    index = next(
                        iter_pads(
                            chainable_first=chainable_first,
                            chainable_only=chainable_only,
                        )
                    )[0]
                except StopIteration as e:
                    raise FiltergraphPadNotFoundError(
                        f"{index_or_label=} could not be resolve to an unused {pad_type} pad index."
                    ) from e
                n = len(index)
                if n < 3:
                    index = (*(0,) * (3 - n), *index)
            elif not self._check_partial_pad_index(index, is_input=is_input):
                raise FiltergraphPadNotFoundError(
                    f"{index_or_label=} cannot be resolve to a valid {pad_type} pad index."
                )
            return index

        # validate
        if (
            self._input_pad_is_available if is_input else self._output_pad_is_available
        )(index):
            return index

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

    def _attach(
        self,
        is_input: bool,
        other: fgb.abc.FilterGraphObject,
        index: PAD_INDEX | list[PAD_INDEX],
        other_index: PAD_INDEX | list[PAD_INDEX],
    ) -> fgb.Chain | fgb.Graph:
        """helper function attach other filtergraph to this graph

        :param is_input: True to attach other to the right
        :param other: other filtergraph object to attach
        :param index: full pad index of this object to attach the other. If multiple
                      links must be made, supply all the indices as a list
        :param other_index: full pad index of the other object to  be attached to this.
                            If multiple links must be made, supply all the indices
                            as a list.
        :return: Joined filtergraph object
        """

        # same operation for Filter & Chain

        if isinstance(other, fgb.Graph):
            return other._attach(not is_input, self, other_index, index)

        if not (isinstance(index, list) or isinstance(other_index, list)):
            left, right, left_index, right_index = (
                (self, other, index, other_index)
                if is_input
                else (other, self, other_index, index)
            )

            if left._output_pad_is_chainable(
                left_index
            ) and right._input_pad_is_chainable(right_index):
                return left._chain(True, right, left[0], right[0])

        return fgb.as_filtergraph(self)._attach(is_input, other, index, other_index)
