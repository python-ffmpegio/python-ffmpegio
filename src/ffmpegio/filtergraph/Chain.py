from __future__ import annotations

from collections import UserList
from collections.abc import Callable, Generator, Sequence

from .. import filtergraph as fgb
from . import utils as filter_utils
from .exceptions import (
    FFmpegioError,
    FiltergraphInvalidExpression,
    FiltergraphInvalidIndex,
)
from .typing import PAD_INDEX, Literal

__all__ = ["Chain"]


class Chain(fgb.abc.FilterGraphObject, UserList):
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

        if isinstance(filter_specs, fgb.Graph):
            if not filter_specs.is_simple_chain():
                raise TypeError(
                    "Cannot convert a multi-chain or linked `Graph` object to a `Chain` object"
                )
            filter_specs = filter_specs[0] if len(filter_specs) > 0 else ""

        if isinstance(filter_specs, fgb.Filter):
            filter_specs = [filter_specs]
        elif filter_specs is not None:
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

            filter_specs = (fgb.as_filter(fspec) for fspec in filter_specs)

        UserList.__init__(self, () if filter_specs is None else filter_specs)

    def compose(
        self,
        show_unconnected_inputs: bool = False,
        show_unconnected_outputs: bool = False,
    ):
        """compose filtergraph

        :param show_unconnected_inputs: display [UNC#] on all unconnected input pads, defaults to True
        :param show_unconnected_outputs: display [UNC#] on all unconnected output pads, defaults to True
        """

        return (
            fgb.Graph([self.data]).compose(
                show_unconnected_inputs, show_unconnected_outputs
            )
            if show_unconnected_inputs or show_unconnected_outputs
            else filter_utils.compose_graph([self.data])
        )

    def __repr__(self):
        type_ = type(self)
        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{self.compose(True, True)}\"
    Number of filters: {len(self.data)}
    Input pads ({self.get_num_inputs()}): {", ".join((str(id) for id, *_ in self.iter_input_pads()))}
    Output pads: ({self.get_num_outputs()}): {", ".join((str(id) for id, *_ in self.iter_output_pads()))}
"""

    def __getitem__(
        self, key: int | slice | tuple[int | slice, int | slice]
    ) -> fgb.Filter:
        if not isinstance(key, (int, slice)):
            i, key = key
            if i != 0:
                raise IndexError("Invalid chain index")

        return UserList.__getitem__(self, key)

    def __setitem__(self, key, value):
        UserList.__setitem__(self, key, fgb.as_filter(value))

    def get_num_chains(self) -> int:
        """get the number of chains"""
        return 1

    def get_num_filters(self, chain: int | None = None) -> int:
        """get the number of filters of the specfied chain

        :param chain: id of the chain, defaults to None to get the total number
                      of filters across all chains
        """

        if chain:
            raise ValueError(f"{chain=} is invalid. Filter object only has 1 chain.")
        return len(self)

    def get_num_inputs(self) -> int:
        return len(list(self.iter_input_pads()))

    def get_num_outputs(self) -> int:
        return len(list(self.iter_output_pads()))

    def is_last_filter(self, filter_id: int) -> bool:
        """Returns True if the given id is the last filter of the chain"""
        return filter_id == len(self) - 1

    def normalize_pad_index(
        self, input: bool, index: PAD_INDEX
    ) -> tuple[int, int, int]:
        """normalize pad index.

        Returns three-element pad index with non-negative indices.

        :param input: True to check the input pad index, False the output.
        :param index: pad index to be normalized
        :return: normalized pad index
        """

        if isinstance(index, int):
            index = (0, 0, index)
        elif len(index) == 1:
            index = (0, 0, *index)
        else:
            if len(index) == 2:
                index = (0, *index)
            if index[-2] < 0:
                index = (index[-3], len(self) + index[-2], index[-1])

        return self[index[1]].normalize_pad_index(input, index)

    def add_label(
        self,
        label: str,
        inpad: PAD_INDEX = None,
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

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        # must convert to FilterGraph as it's the only object with labels
        fg = fgb.Graph([self])
        return fg.add_label(label, inpad, outpad, force)

    def append(self, item):
        return UserList.append(self, fgb.as_filter(item))

    def extend(self, other: fgb.Chain | Sequence[fgb.Filter | str]):
        return UserList.extend(self, [fgb.as_filter(f) for f in other])

    def insert(self, i, item):
        return UserList.insert(self, i, fgb.as_filter(item))

    def __contains__(self, item):
        item = fgb.as_filter(item)
        return any((f == item for f in self.data))

    def __ior__(self, other):
        raise Chain.Error("cannot assign operation outcome which is not a filterchain")

    def __iadd__(self, other):

        if len(other):
            fg = self + other if len(self) else Chain(other)

            if isinstance(fg, fgb.Graph):
                raise Chain.Error(
                    "cannot assign operation outcome which is not a filterchain"
                )
            self.data = fg.data
        return self

    def __irshift__(self, other):
        if len(other):
            fg = self >> other if len(self) else Chain(other)

            if isinstance(fg, fgb.Graph):
                raise Chain.Error(
                    "cannot assign operation outcome which is not a filterchain"
                )
            self.data = fg.data
            return self

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

        if not len(self):
            return

        if skip_if_no_input and self.next_input_pad() is None:
            return

        if skip_if_no_output and self.next_output_pad() is None:
            return

        yield (0, self)

    def _iter_pads(
        self,
        iter_filter_pad: Callable,
        i_nochain: int,
        pad: int | None,
        filter: int | None,
        chain: Literal[0] | None,
        exclude_chainable: bool,
        chainable_first: bool,
        include_connected: bool,
        chainable_only: bool,
    ) -> Generator[tuple[PAD_INDEX, fgb.Filter, bool]]:
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

        if isinstance(chain, int) and chain != 0:
            # Filterchain has only one chain.
            raise FiltergraphInvalidIndex(f"Invalid {chain=} id")

        if chainable_only:
            if filter is not None:
                if filter < 0:
                    filter = len(self) + filter
                if filter != i_nochain:
                    raise FiltergraphInvalidIndex(
                        f"{filter=} id is not chainable filter."
                    )
            filters = [self.data[i_nochain]]
            i_first = i_nochain

        elif filter is None:
            # iterate over all filters
            filters = self.data
            i_first = 0
        else:
            try:
                filters = [self.data[filter]]
            except IndexError:
                raise FiltergraphInvalidIndex(f"Invalid {filter=} id.")
            i_first = filter

        # iterate over all filters
        for i, f in enumerate(filters):
            no_chainables = (not include_connected and i != i_nochain) or (
                exclude_chainable and i == i_nochain
            )
            try:
                for pidx, f, other_pidx in iter_filter_pad(
                    f,
                    pad,
                    exclude_chainable=no_chainables,
                    chainable_first=chainable_first,
                    chainable_only=chainable_only,
                ):
                    yield (i + i_first, *pidx), f, other_pidx
            except FiltergraphInvalidIndex:
                pass

    def iter_input_pads(
        self,
        pad: int | None = None,
        filter: int | None = None,
        chain: Literal[0] | None = None,
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
        """Iterate over input pads of the filters on the filterchain

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
        :param full_pad_index: True to return 3-element index
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        for index, filter, other_index in self._iter_pads(
            fgb.Filter.iter_input_pads,
            0,
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
            chainable_only,
        ):
            if other_index is None:
                out_index = None
            else:
                # get the last output pad of the previous filter
                out_i = index[1] - 1
                out_index = (0, out_i, self[out_i].get_num_outputs() - 1)

            yield (
                ((0, *index), filter, out_index)
                if full_pad_index
                else (index, filter, out_index)
            )

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
        """Iterate over output pads of the filters on the filterchain

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last output pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last output first then the rest, defaults to False
        :param include_connected: True to include pads connected to output streams, defaults to False
        :param unlabeled_only: True to leave out named outputs, defaults to False to return all outputs
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all outputs
        :param full_pad_index: True to return 3-element index
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        for index, filter, other_index in self._iter_pads(
            fgb.Filter.iter_output_pads,
            len(self.data) - 1,
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            include_connected,
            chainable_only,
        ):
            if other_index is None:
                in_index = None
            else:
                # get the last input pad of the next filter
                in_i = index[1] + 1
                in_index = (0, in_i, self[in_i].get_num_inputs() - 1)
            yield (
                ((0, *index), filter, in_index)
                if full_pad_index
                else (index, filter, in_index)
            )

    def connect(
        self,
        right: fgb.abc.FilterGraphObject,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        *,
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | fgb.Chain | None:
        """combine another filtergraph object and make downstream connections (worker)

        :param right: other filtergraph
        :param fwd_links: a list of tuples, pairing self's output pad and right's input pad
        :param bwd_links: a list of tuples, pairing right's output pad and self's input pad
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

        :param inplace: ``True`` to add the ``right`` graph in place.
        :return: new filtergraph object

        * link labels may be auto-renamed if there is a conflict

        """

        return self._connect(
            fgb.Graph.connect,
            right,
            from_left,
            to_right,
            from_right,
            to_left,
            chain_siso,
            sws_flags_policy,
            inplace,
        )

    def rconnect(
        self,
        left: fgb.abc.FilterGraphObject,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        *,
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None = None,
        chain_siso: bool = True,
        sws_flags_policy: Literal["first", "last"] | int | None = None,
        inplace: bool = False,
    ) -> fgb.Graph | fgb.Chain | None:
        """combine another filtergraph object and make downstream connections (worker)

        :param left: other filtergraph
        :param fwd_links: a list of tuples, pairing self's output pad and right's input pad
        :param bwd_links: a list of tuples, pairing right's output pad and self's input pad
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

        :param inplace: ``True`` to add the ``right`` graph in place.
        :return: new filtergraph object

        * link labels may be auto-renamed if there is a conflict

        """

        return self._connect(
            fgb.Graph.rconnect,
            left,
            from_left,
            to_right,
            from_right,
            to_left,
            chain_siso,
            sws_flags_policy,
            inplace,
        )

    def _connect(
        self,
        graph_connect,  # fgb.Graph.connect or fgb.Graph.rconnect
        other: fgb.abc.FilterGraphObject,
        from_left: PAD_INDEX | str | list[PAD_INDEX | str],
        to_right: PAD_INDEX | str | list[PAD_INDEX | str],
        from_right: PAD_INDEX | str | list[PAD_INDEX | str] | None,
        to_left: PAD_INDEX | str | list[PAD_INDEX | str] | None,
        chain_siso: bool,
        sws_flags_policy: Literal["first", "last"] | int | None,
        inplace: bool,
    ) -> fgb.Graph | fgb.Chain | None:
        """helper for connect and rconnect"""

        fg = graph_connect(
            fgb.as_filtergraph(self),
            other,
            from_left,
            to_right,
            from_right=from_right,
            to_left=to_left,
            chain_siso=chain_siso,
            sws_flags_policy=sws_flags_policy,
            inplace=False,
        )

        return self._convert_graph(inplace, fg)

    def _convert_graph(self, inplace, fg):
        if not inplace:
            return fg[0] if fg.is_simple_chain() else fg

        if isinstance(fg, fgb.Chain):
            self.clear()
            self.extend(fg)
        elif fg.is_simple_chain():
            self.clear()
            if len(fg):
                self.extend(fg[0])
        else:
            raise ValueError(
                "'inplace=True' but resulting filtergraph is not a simple chain."
            )

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

        if chainable_only == "auto":
            chainable_only = True

        try:
            assert left_on is None and right_on is None and chainable_only is True
            right_obj = fgb.as_filterchain(right)
        except (AssertionError, FiltergraphInvalidExpression):
            return self._convert_graph(
                inplace,
                fgb.as_filtergraph(self).attach(
                    right,
                    left_on,
                    right_on,
                    chainable_only=chainable_only,
                    chain_siso=chain_siso,
                    inplace=False,
                ),
            )

        left_pad = next(self.iter_output_pads(chainable_only=True))
        right_pad = next(right_obj.iter_input_pads(chainable_only=True))
        return self.connect(
            right_obj, left_pad, right_pad, chain_siso=chain_siso, inplace=inplace
        )

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

        :param left: input filtergraph or labels
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

        if chainable_only == "auto":
            chainable_only = True

        try:
            assert left_on is None and right_on is None and chainable_only is True
            left_obj = fgb.as_filterchain(left)
        except (AssertionError, FiltergraphInvalidExpression):
            return self._convert_graph(
                inplace,
                fgb.as_filtergraph(self).rattach(
                    left,
                    left_on,
                    right_on,
                    chainable_only=chainable_only,
                    chain_siso=chain_siso,
                    inplace=False,
                ),
            )

        left_pad = next(left_obj.iter_output_pads(chainable_only=True))
        right_pad = next(self.iter_input_pads(chainable_only=True))
        return self.connect(
            left_obj, left_pad, right_pad, chain_siso=chain_siso, inplace=inplace
        )

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
