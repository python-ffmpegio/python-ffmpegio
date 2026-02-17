from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator, Sequence

from .. import filtergraph as fgb
from .exceptions import *
from .GraphLinks import GraphLinks
from .typing import JOIN_HOW, PAD_INDEX, Literal

__all__ = ["FilterGraphObject"]


class FilterGraphObject(ABC):
    @staticmethod
    def relabel_duplicates(*fgs: tuple[FilterGraphObject]): ...

    def relabel(self, labels: dict[str | int, str | int]): ...

    @property
    def links(self) -> GraphLinks | None:
        """filtergraph link definition only if filtergraph"""
        return None

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

    @abstractmethod
    def get_num_chains(self) -> int:
        """get the number of chains"""

    @abstractmethod
    def get_num_filters(self, chain: int | None = None) -> int:
        """get the number of filters of the specfied chain

        :param chain: id of the chain, defaults to None to get the total number
                      of filters across all chains
        """

    def next_input_pad(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: int | None = None,
        chainable_first: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
        full_pad_index: bool = False,
        exclude_indices: Sequence[PAD_INDEX] | None = None,
    ) -> PAD_INDEX | None:
        """get next available input pad

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param chainable_first: True to retrieve the last pad first, then the rest sequentially, defaults to False
        :param unlabeled_only: True to retrieve only unlabeled pad, defaults to False
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all inputs
        :param full_pad_index: True to return 3-element index, defaults to False
        :param exclude_indices: List pad indices to skip, defaults to None to allow all
        :returns: The index of the pad or ``None`` if no pad found
        """

        if exclude_indices is None:
            exclude_indices = ()

        try:
            return next(
                (
                    idx
                    for idx, *_ in self.iter_input_pads(
                        pad,
                        filter,
                        chain,
                        chainable_first=chainable_first,
                        unlabeled_only=unlabeled_only,
                        chainable_only=chainable_only,
                        full_pad_index=full_pad_index,
                    )
                    if idx not in exclude_indices
                )
            )
        except StopIteration:
            return None

    def next_output_pad(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: int | None = None,
        chainable_first: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
        full_pad_index: bool = False,
        exclude_indices: Sequence[PAD_INDEX] | None = None,
    ) -> PAD_INDEX | None:
        """get next available output pad

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param chainable_first: True to retrieve the last pad first, then the rest sequentially, defaults to False
        :param unlabeled_only: True to retrieve only unlabeled pad, defaults to False
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all inputs
        :param full_pad_index: True to return 3-element index, defaults to False
        :param exclude_indices: List pad indices to skip, defaults to None to allow all
        :returns: The index of the pad or ``None`` if no pad found
        """

        if exclude_indices is None:
            exclude_indices = ()

        try:
            return next(
                idx
                for idx, *_ in self.iter_output_pads(
                    pad,
                    filter,
                    chain,
                    chainable_first=chainable_first,
                    unlabeled_only=unlabeled_only,
                    chainable_only=chainable_only,
                    full_pad_index=full_pad_index,
                )
                if idx not in exclude_indices
            )
        except StopIteration:
            return None

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
        exclude_stream_specs: bool = False,
        only_stream_specs: bool = False,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
        full_pad_index: bool = False,
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter, PAD_INDEX | None]]:
        """Iterate over input pads of the filter

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_stream_specs: True to not include input streams
        :param only_stream_specs: True to only include input streams
        :param exclude_chainable: True to leave out the last input pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last input first then the rest, defaults to False
        :param include_connected: True to include pads connected to input streams, defaults to False
        :param unlabeled_only: True to leave out named inputs, defaults to False to return all inputs
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all inputs
        :param full_pad_index: True to return 3-element index, defaults to False
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
        full_pad_index: bool = False,
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
        :param full_pad_index: True to return 3-element index, defaults to False
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

    # Label management methods (default operation for non-Graph objects)

    def iter_input_labels(
        self, exclude_stream_specs: bool = False, only_stream_specs: bool = False
    ) -> Generator[tuple[str, PAD_INDEX]]:
        """iterate over the dangling labeled input pads of the filtergraph object

        :param exclude_stream_specs: True to not include input streams
        :param only_stream_specs: True to only include input streams
        :yield: a tuple of 3-tuple pad index and the pad index of the connected output pad if connected
        """

        yield from ()

    def iter_output_labels(self) -> Generator[tuple[str, PAD_INDEX]]:
        """iterate over the dangling labeled output pads of the filtergraph object

        :yield: a tuple of 3-tuple pad index and the pad index of the connected input pad if connected
        """

        yield from ()

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
        if outpad is not None:
            return self._get_label(False, outpad)
        raise ValueError(
            "One and only one of index, inpad, or outpad must be specified."
        )

    def _get_label(self, input: bool, index: PAD_INDEX):
        return None

    @abstractmethod
    def normalize_pad_index(
        self, input: bool, index: PAD_INDEX
    ) -> tuple[int, int, int]:
        """normalize pad index.

        Returns three-element pad index with non-negative indices.

        :param input: True to check the input pad index, False the output.
        :param index: pad index to be normalized
        :return: normalized pad index
        """

    def get_input_pad(
        self, index_or_label: PAD_INDEX | str
    ) -> tuple[PAD_INDEX, str | None]:
        """resolve (unconnected) input pad from pad index or label

        :param index: pad index or link label
        :return: filter input pad index and its link label (None if not assigned)

        Raises error if specified label does not resolve uniquely to an input pad
        """

        index = self.resolve_pad_index(index_or_label, is_input=True)
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

        index = self.resolve_pad_index(index_or_label, is_input=False)
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

    def has_label(
        self, label: str, only_if: Literal["input", "output", "internal"] | None = None
    ) -> bool:
        """True if a linklabel is defined

        :param label: name of the link label
        :param only_if: also check for the type of the label
        :return: True if exists
        """
        return False  # reimplemented by Graph

    def remove_label(self, label: str, inpad: PAD_INDEX | None = None):
        """remove an input/output label

        :param label: linkn label
        :param inpad: specify input pad if multiple pads receives the same input
                      stream, defaults to `None` to delete all input pads.
        """

    ### main graph manipulation routines

    def stack(
        self,
        *others: tuple[fgb.abc.FilterGraphObject | str],
        auto_link: bool | int = False,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | None:
        """stack filtergraph objects

        :param others: other filtergraphs to be stacked under in the order
                       appeared
        :param auto_link: ``True`` to connect matched I/O labels, defaults to
            ``None``
        :param sws_flags_policy: Defines how to set ``sws_flags``:

            * ``'first'``: to use the first ``sws_flags`` found among the
              filtergraphs (searched ``self`` first then ``others``)
            * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
              not set).
            * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
              refers to this object, ``1`` refers to ``others[0]``, etc.
            * ``None``: if more than one have the ``sws_flags`` set, raises
              ``FFmpegioError`` exception. Otherwise, it uses the only one found
              or none if none not found.

        :param inplace: Must be ``False`` as the result is always a ``Graph``.
            If ``True``, a ``ValueError` exception will be raised.
        :return: new filtergraph object

        Remarks
        -------
        - extend() and import links
        - If `auto-link=False`, common labels may be renamed.
        - For more explicit linking rather than the auto-linking, use `connect()` instead.

        """

        if inplace:
            raise ValueError("Filter object cannot perform stack() with inplace=True")

        return fgb.as_filtergraph(self).stack(*others, auto_link, sws_flags_policy)

    @abstractmethod
    def connect(
        self,
        right: fgb.abc.FilterGraphObject | str,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        *,
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | fgb.Chain | None:
        """append another filtergraph object and make downstream connections

        :param right: receiving filtergraph object
        :param from_left: output pad ids or labels of `left` fg
        :param to_right: input pad ids or labels of the `right` fg
        :param from_right: output pad ids or labels of the `right` fg
        :param to_left: input pad ids or labels of this `left` fg
        :param chain_siso: ``True`` (default) to chain the connections instead
            of stacking. ``False`` to append all the chains of ``right`` graphs.
        :param sws_flags_policy: Defines how to set ``sws_flags``:

            * ``'first'``: to use the first ``sws_flags`` found among the
              filtergraphs (searched ``self`` first then ``others``)
            * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
              not set).
            * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
              refers to this object, ``1`` refers to ``others[0]``, etc.
            * ``None``: if more than one have the ``sws_flags`` set, raises
              ``FFmpegioError`` exception. Otherwise, it uses the only one found
              or none if none not found.

        :param inplace: ``True`` to store the output filtergraph in place.
            If ``'inplace=True`` but the output is not of the same class type,
            a ``ValueError` exception will be raised.
        :return: new filtergraph object or ``None`` if ``inplace=True``

        * link labels may be auto-renamed if there is a conflict

        """

    @abstractmethod
    def rconnect(
        self,
        left: fgb.abc.FilterGraphObject | str,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        *,
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | fgb.Chain | None:
        """append another filtergraph object and make upstream connections

        :param left: transmitting filtergraph object
        :param right: receiving filtergraph object
        :param from_left: output pad ids or labels of `left` fg
        :param to_right: input pad ids or labels of the `right` fg
        :param from_right: output pad ids or labels of the `right` fg
        :param to_left: input pad ids or labels of this `left` fg
        :param chain_siso: ``True`` (default) to chain the connections instead
            of stacking. ``False`` to append all the chains of ``right`` graphs.
        :param replace_sws_flags: Defines how to set ``sws_flags``:

            * ``True``: to use the first ``sws_flags`` found among the
              filtergraphs, chosen in the order of appearance
            * ``False``: use this filtergraph's ``sws_flags`` (or none used if
              not set).
            * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
              refers to this object, ``1`` refers to ``others[0]``, etc.
            * ``None``: if more than one have the ``sws_flags`` set, raises
              ``FFmpegioError`` exception. Otherwise, it uses the only one found
              or none if none not found.

        :param inplace: ``True`` to store the output filtergraph in place.
            If ``'inplace=True`` but the output is not of the same class type,
            a ``ValueError` exception will be raised.
        :return: new filtergraph object or ``None`` if ``inplace=True``

        * link labels may be auto-renamed if there is a conflict

        """

    def join(
        self,
        right: fgb.abc.FilterGraphObject | str,
        *,
        how: JOIN_HOW | None = None,
        n_links: int | Literal["all"] | None = None,
        strict: bool = False,
        unlabeled_only: bool = False,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | fgb.Chain:
        """filtergraph auto-connector

        :param right: receiving filtergraph object
        :param how: method on how to mate input and output, defaults to ``"per_chain"``.

            - ``'chainable'``: joins only chainable input pads and output pads.
            - ``'per_chain'``: joins one pair of first available input pad and output pad of each
                                mating chains. Source and sink chains are ignored.
            - ``'all'``: joins all input pads and output pads
            - ``'auto'``: tries ``'per_chain'`` first, if fails, then tries ``'all'``.

        :param n_links: number of left output pads to be connected to the right input pads, default: 0
                        (all matching links). If ``how=='per_chain'``, ``n_links`` connections are made
                        per chain.
        :param strict: True to raise exception if numbers of available pads do not match, default: False
        :param unlabeled_only: True to ignore labeled unconnected pads, defaults to False
        :param chain_siso: True to chain the single-input single-output connection, default: True
        :param sws_flags_policy: Defines how to set ``sws_flags``:

            * ``'first'``: to use the first ``sws_flags`` found among the
                filtergraphs (searched ``self`` first then ``others``)
            * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
                not set).
            * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
                refers to this object, ``1`` refers to ``others[0]``, etc.
            * ``None``: if more than one have the ``sws_flags`` set, raises
                ``FFmpegioError`` exception. Otherwise, it uses the only one found
                or none if none not found.

        :return: Graph with the appended filter chains or None if inplace=True.
        """

        right = fgb.as_filtergraph_object(right)

        # if one of the filtergraphs is empty, return the other (or a copy thereof)
        if right.get_num_filters() == 0:
            return None if inplace else self.copy()
        if self.get_num_filters() == 0:
            if inplace:
                self.__init__(right)
                return
            else:
                return right.copy()

        from_left, to_right = self._join_analyze(
            self,
            right,
            how,
            n_links,
            strict,
            unlabeled_only,
        )

        return self.connect(
            right,
            from_left=from_left,
            to_right=to_right,
            chain_siso=chain_siso,
            sws_flags_policy=sws_flags_policy,
            inplace=inplace,
        )

    def rjoin(
        self,
        left: fgb.abc.FilterGraphObject | str,
        *,
        how: JOIN_HOW | None = None,
        n_links: int | Literal["all"] | None = None,
        strict: bool = False,
        unlabeled_only: bool = False,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | fgb.Chain:
        """filtergraph auto-connector

        :param left: feeding filtergraph object
        :param how: method on how to mate input and output, defaults to ``"per_chain"``.

            - ``'chainable'``: joins only chainable input pads and output pads.
            - ``'per_chain'``: joins one pair of first available input pad and output pad of each
                                mating chains. Source and sink chains are ignored.
            - ``'all'``: joins all input pads and output pads
            - ``'auto'``: tries ``'per_chain'`` first, if fails, then tries ``'all'``.

        :param n_links: number of left output pads to be connected to the right input pads, default: 0
                        (all matching links). If ``how=='per_chain'``, ``n_links`` connections are made
                        per chain.
        :param strict: True to raise exception if numbers of available pads do not match, default: False
        :param unlabeled_only: True to ignore labeled unconnected pads, defaults to False
        :param chain_siso: ``True`` to chain the single-input single-output
            connection, default: True
        :param sws_flags_policy: Defines how to set ``sws_flags``:

            * ``'first'``: to use the first ``sws_flags`` found among the
                filtergraphs (searched ``self`` first then ``others``)
            * ``'last'``: use this filtergraph's ``sws_flags`` (or none used if
                not set).
            * ``int``: specify which filtergraph's ``sws_flags`` to use. ``0``
                refers to this object, ``1`` refers to ``others[0]``, etc.
            * ``None``: if more than one have the ``sws_flags`` set, raises
                ``FFmpegioError`` exception. Otherwise, it uses the only one found
                or none if none not found.

        :return: Graph with the appended filter chains or None if inplace=True.
        """

        left = fgb.as_filtergraph_object(left)

        # if one of the filtergraphs is empty, return the other (or a copy thereof)
        if left.get_num_filters() == 0:
            return None if inplace else self.copy()
        if self.get_num_filters() == 0:
            if inplace:
                self.__init__(left)
                return
            else:
                return left.copy()

        from_left, to_right = self._join_analyze(
            left, self, how, n_links, strict, unlabeled_only
        )

        return self.rconnect(
            left,
            from_left=from_left,
            to_right=to_right,
            chain_siso=chain_siso,
            sws_flags_policy=sws_flags_policy,
            inplace=inplace,
        )

    @staticmethod
    def _join_analyze(
        left: FilterGraphObject,
        right: FilterGraphObject,
        how: JOIN_HOW | None,
        n_links: int | Literal["all"] | None,
        strict: bool,
        unlabeled_only: bool,
    ):
        if how is None:
            how = "auto"
        if n_links is None:
            n_links = "all"

        if how not in get_args(JOIN_HOW):
            raise ValueError(f"{how=} is not a valid option")

        # handle joining empty graph
        nright = right.get_num_chains()
        nleft = left.get_num_chains()

        iter_kws = {"unlabeled_only": unlabeled_only, "full_pad_index": True}
        if how == "chainable":
            iter_kws["chainable_only"] = True

        if n_links == "all" or n_links < 0:
            n_links = 0

        from_left = []
        to_right = []

        if how in ("per_chain", "auto") and nright == nleft:
            try:
                from_left = [
                    next(left.iter_output_pads(chain=c, **iter_kws))[0]
                    for c in range(nleft)
                ]
                to_right = [
                    next(right.iter_input_pads(chain=c, **iter_kws))[0]
                    for c in range(nleft)
                ]

            except StopIteration:
                if how == "auto":
                    how = "all"
                else:
                    raise

        if how in ("all", "chainable") or nright != nleft:
            left_pads = [out[0] for out in left.iter_output_pads(**iter_kws)]
            right_pads = [out[0] for out in right.iter_input_pads(**iter_kws)]

            nleft, nright = len(left_pads), len(right_pads)
            if strict and nleft != nright:
                raise FFmpegioError(
                    "`[stict=True] number of unconnected pads must match."
                )
            n_max = min(nleft, nright)
            n_links = n_max if n_links <= 0 else min(n_links, n_max)

            from_left = left_pads[:n_links]
            to_right = right_pads[:n_links]
        return from_left, to_right

    @abstractmethod
    def attach(
        self,
        right: fgb.abc.FilterGraphObject | str | list[str],
        left_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        right_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        *,
        chainable_only: bool | Literal["left", "right", "auto"] = "auto",
        chain_siso: bool = True,
        inplace: bool = False,
    ) -> fgb.Chain | fgb.Graph:
        """attach filter, chain, graph, or labels to available output pads

        :param right: output filtergraph or labels. If ``str``, the expression
            is first attempted to be converted to a filtergraph object. If the
            attempt fails, it is treated as a label.
        :param left_on: pad_index, specify the output pad to connect ``right``
            to, defaults to auto-detect (first available)
        :param right_on: pad index, specifies the input pad of ``right`` to
            connect to the ``left_on`` pad, defaults to auto-detect (first
            available)
        :param chainable_only: ``True`` to limit auto-detecting ``left_on`` and
            ``righ_on`` pads to be only those that can extend the existing
            chains. To force this condition only on one side, use ``'left'`` or
            ``'right'``. If ``"auto"`` (default) depends on this filtergraph
            object type: ``Filter`` and ``Chain`` defaults to ``True`` while
            ``Graph`` defaults to ``False``
        :param chain_siso: ``True`` (default) to chain the new connection,
            ``False`` to stack attached filtergraph.
        :param inplace: ``True`` to store the output filtergraph in place.
            If ``'inplace=True`` but the output is not of the same class type,
            a ``ValueError` exception will be raised.
        :return: new filtergraph object or ``None`` if ``inplace=True``

        """

    @abstractmethod
    def rattach(
        self,
        left: fgb.abc.FilterGraphObject | str | list[str],
        left_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        right_on: PAD_INDEX | str | list[PAD_INDEX | str | None] | None = None,
        *,
        chainable_only: bool | Literal["left", "right", "auto"] = "auto",
        chain_siso: bool = True,
        inplace: bool = False,
    ) -> fgb.Chain | fgb.Graph:
        """attach filter, chain, graph, or labels to available input pads

        :param left: input filtergraph or labels. If ``str``, the expression
            is first attempted to be converted to a filtergraph object. If the
            attempt fails, it is treated as a label.
        :param left_on: pad_index, specify the output pad of ``left``,
            defaults to auto-detect (first available)
        :param right_on: pad index, specifies which input pad to connect
            ``left`` to, defaults to auto-detect (first available)
        :param chainable_only: ``True`` to limit auto-detecting ``left_on`` and
            ``righ_on`` pads to be only those that can extend the existing
            chains. To force this condition only on one side, use ``'left'`` or
            ``'right'``. If ``"auto"`` (default) depends on this filtergraph
            object type: ``Filter`` and ``Chain`` defaults to ``True`` while
            ``Graph`` defaults to ``False``
        :param chain_siso: ``True`` (default) to chain the new connection,
            ``False`` to stack attached filtergraph.
        :param inplace: ``True`` to store the output filtergraph in place.
            If ``'inplace=True`` but the output is not of the same class type,
            a ``ValueError` exception will be raised.
        :return: new filtergraph object or ``None`` if ``inplace=True``

        """

    ### main graph manipulation routines

    @abstractmethod
    def __getitem__(self, key): ...

    @abstractmethod
    def compose(
        self,
        show_unconnected_inputs: bool = True,
        show_unconnected_outputs: bool = True,
    ):
        """compose filtergraph

        :param show_unconnected_inputs: display [UNC#] on all unconnected input pads, defaults to True
        :param show_unconnected_outputs: display [UNC#] on all unconnected output pads, defaults to True

        """

    # def __eq__(self, value: FilterGraphObject | str) -> bool:
    def __eq__(self, value: object) -> bool:

        try:
            value = fgb.convert.as_filtergraph_object_like(value, self)
        except Exception:
            return False

        return super().__eq__(value)

    # def __ne__(self, value: FilterGraphObject | str) -> bool:
    def __ne__(self, value: object) -> bool:
        try:
            value = fgb.convert.as_filtergraph_object_like(value, self)
        except Exception:
            return True

        return super().__ne__(value)

    def __str__(self) -> str:
        return self.compose(False, False)

    @abstractmethod
    def __repr__(self) -> str: ...

    # Filtergraph math operators

    def __add__(self, other: FilterGraphObject | str) -> fgb.Chain | fgb.Graph:
        return fgb.join(self, other, inplace=False)

    def __radd__(self, other: FilterGraphObject | str) -> fgb.Chain | fgb.Graph:
        return fgb.join(other, self, inplace=False)

    def __mul__(self, __n: int) -> fgb.Graph:
        """duplicate-n-stack"""
        if not isinstance(__n, int):
            return NotImplemented
        return fgb.stack(*((self,) * __n), inplace=False)

    def __rmul__(self, __n: int) -> fgb.Graph:
        """duplicate-n-stack"""
        if not isinstance(__n, int):
            return NotImplemented
        return fgb.stack(*((self,) * __n), inplace=False)

    def __or__(self, other: FilterGraphObject | str) -> fgb.Graph:
        """stack"""
        return fgb.stack(self, other, inplace=False)

    def __ror__(self, other: FilterGraphObject | str) -> fgb.Graph:
        """stack"""
        return fgb.stack(other, self, inplace=False)

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

        def parse_other(other):
            if not isinstance(other, fgb.Filter) and isinstance(other, tuple):
                if len(other) > 2:
                    index, other_index, other = other
                else:
                    index, other = other
                    other_index = None
            else:
                index = other_index = None

            return other, index, other_index

        # if output is a list
        if isinstance(other, list):
            if len(other) == 0:
                raise ValueError("At least one `other` filtergraph must be specified.")

            # match the pad indices first
            right, left_on, right_on = [
                [*t] for t in zip(*(parse_other(o) for o in other))
            ]
        else:
            # parse other argument, separate the indices if given
            right, left_on, right_on = parse_other(other)

        return fgb.attach(self, right, left_on, right_on, inplace=False)

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

        def parse_other(other):
            if not isinstance(other, fgb.Filter) and isinstance(other, tuple):
                if len(other) > 2:
                    other, other_index, index = other
                else:
                    other, index = other
                    other_index = None
            else:
                index = other_index = None

            return other, index, other_index

        # if output is a list
        if isinstance(other, list):
            if len(other) == 0:
                raise ValueError("At least one `other` filtergraph must be specified.")

            # match the pad indices first
            left, right_on, left_on = [
                [*t] for t in zip(*(parse_other(o) for o in other))
            ]
        else:
            # parse other argument, separate the indices if given
            left, right_on, left_on = parse_other(other)

        return fgb.attach(left, self, left_on, right_on, inplace=False)

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
                            chain=index[0],
                            filter=index[1],
                            pad=index[2],
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

    def resolve_pad_indices(
        self,
        indices_or_labels: Sequence[PAD_INDEX | str | None],
        *,
        is_input: bool = True,
        resolve_omitted: bool = True,
        chainable_first: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
    ) -> list[PAD_INDEX]:
        """Resolve unconnected labels or pad indices to full 3-element pad indices

        :param indices_or_labels: a list of pad indices or pad labels or ``None`` to auto-select
        :param is_input: True to resolve an input pad, else an output pad, defaults to True
        :param chainable_first: if True, chainable pad is selected first, defaults to False
        :param unlabeled_only: True to retrieve only unlabeled pad, defaults to False
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all pads

        One and only one of ``index`` and ``label`` must be specified. If the given index
        or label is invalid, it raises FiltergraphPadNotFoundError.

        Omitted pads

        """

        # resolve all the specified pad indices of the self object
        indices = [
            (
                self.resolve_pad_index(
                    idx,
                    is_input=is_input,
                    chain_id_omittable=True,
                    filter_id_omittable=True,
                    pad_id_omittable=True,
                    resolve_omitted=False,
                )
            )
            for idx in indices_or_labels
        ]

        if resolve_omitted:
            # assign unknown pad indices in the order of the following ranking:
            # indices ranking
            # - int, int, int    = 3*6 = 18
            # - int, int, None   = 2*5 = 10
            # - int, None, int   = 2*4 = 8
            # - None, int, int   = 2*3 = 6
            # - int, None, None  = 1*3 = 3
            # - None, int, None  = 1*2 = 2
            # - None, None, int  = 1*1 = 1
            # - None, None, None = 0*0 = 0

            index_scores = [
                (
                    sum(i is not None for i in index)
                    * sum((3 - j) for j, i in enumerate(index) if i is not None)
                )
                for index in indices
            ]
            index_assign_order = sorted(
                range(len(index_scores)), key=index_scores.__getitem__, reverse=True
            )

            next_base_pad = self.next_input_pad if is_input else self.next_output_pad
            known_indices = set()
            for i in index_assign_order:
                if index_scores[i] < 18:
                    chain, filter, pad = indices[i]
                    pad = next_base_pad(
                        chain=chain,
                        filter=filter,
                        pad=pad,
                        chainable_first=chainable_first,
                        unlabeled_only=unlabeled_only,
                        chainable_only=chainable_only,
                        full_pad_index=True,
                        exclude_indices=known_indices,
                    )
                    if pad is None:
                        raise ValueError("No more available filter pad found.")
                    indices[i] = pad

                known_indices.add(indices[i])
        elif len(indices) != len(set(indices)):
            raise FiltergrapDuplicatehPadFoundError()

        return indices

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
        right: list[fgb.Filter | fgb.Chain | str],
        left_on: list[PAD_INDEX],
        right_on: list[PAD_INDEX | None],
    ) -> fgb.Chain | fgb.Graph:
        """helper function attach other filtergraph to this graph

        :param right: list of filter/chain objects or pad label strings
        :param left_on: list of output pad indices, matching the size of right
        :param right_on: list of input pad indices if object or None if label
        :param right_first: True to preserve the chain indices of the right filtergraph object, defaults
                            to False to preserve the chain order of the self object
        :return: resulting filtergraph
        """

        fg = (
            fgb.as_filtergraph(self)
            if any(idx is None for idx in right_on)
            else fgb.atleast_filterchain(self)
        )
        for r, l_idx, r_idx in zip(right, left_on, right_on, strict=True):
            if r_idx is None:  # label
                fg.add_label(r, outpad=l_idx)
            else:
                out = fg._connect(r, [(l_idx, r_idx)], [], chain_siso=True)
                if out == NotImplemented:
                    raise ValueError("right fg objects include a graph.")
                fg = out
        return fg

    def _rattach(
        self,
        left: list[fgb.Filter | fgb.Chain | str],
        left_on: list[PAD_INDEX | None],
        right_on: list[PAD_INDEX],
    ) -> fgb.Chain | fgb.Graph:
        """helper function attach other filtergraph to this graph

        :param right: list of filter/chain objects or pad label strings
        :param left_on: list of output pad indices if object or None if label, size must match that of left
        :param right_on: list of input pad indices, matching the size of left
        :param right_first: True to preserve the chain indices of the left filtergraph object, defaults
                            to False to preserve the chain order of the self object
        :return: resulting filtergraph
        """

        # fg = (
        #     fgb.as_filtergraph(self)
        #     if any(idx is None for idx in left_on)
        #     else fgb.atleast_filterchain(self)
        # )

        if not len(left):
            return type(self)(self)

        # find chain offset after stacking
        nleft = 0
        n0 = [
            0,
            *(
                nleft := nleft + (0 if l_idx is None else (l.get_num_chains()))
                for l, l_idx in zip(left, left_on)
            ),
        ]

        # combine the left filtergraphs first
        left_fgs = [l for l in left if not isinstance(l, str)]
        fg = (
            fgb.stack(*left_fgs)
            if nleft > 1 or isinstance(self, fgb.Graph)
            else (
                fgb.as_filtergraph_object(left_fgs[0], copy=True)
                if len(left_fgs)
                else fgb.Chain()
            )
        )

        # adjust left pad indices
        left_on = [idx and (idx[0] + n, *idx[1:]) for idx, n in zip(left_on, n0)]

        if len(fg):
            # connect stacked left and right
            out = fg._connect(
                self,
                [
                    (lidx, ridx)
                    for lidx, ridx in zip(left_on, right_on, strict=True)
                    if lidx is not None
                ],
                [],
                chain_siso=True,
            )
            if out == NotImplemented:
                raise ValueError("right fg objects include a graph.")
        else:
            out = fgb.as_filtergraph_object(self, copy=True)

        # add labels to the combined graph
        for l, l_idx, r_idx in zip(left, left_on, right_on):
            if l_idx is None:  # label
                out = out.add_label(l, inpad=(r_idx[0] + nleft, *r_idx[1:]))

        return out
