from __future__ import annotations

import re
from collections.abc import Generator, Sequence
from functools import cached_property, partial

from .. import filtergraph as fgb
from ..caps import FilterInfo, filter_info, layouts
from ..stream_spec import parse_stream_spec
from . import utils as filter_utils
from .exceptions import *
from .typing import PAD_INDEX, Literal

__all__ = ["Filter"]


class Filter(fgb.abc.FilterGraphObject, tuple):
    """FFmpeg filter definition immutable class

    :param filter_spec: _description_
    :type filter_spec: _type_
    :param filter_id: _description_, defaults to None
    :type filter_id: _type_, optional
    :param \\*opts: filter option values assigned in the order options are
                    declared
    :type \\*opts: dict, optional
    :param \\**kwopts: filter options in key=value pairs
    :type \\**kwopts: dict, optional

    """

    class Error(FFmpegioError):
        pass

    class InvalidName(Error):
        def __init__(self, name):
            from .. import path

            super().__init__(
                f"Filter {name} is not defined in FFmpeg (v{path.FFMPEG_VER}).\n"
            )

    class InvalidOption(Error):
        pass

    class Unsupported(Error):
        def __init__(self, name, feature) -> None:
            super().__init__(f"{feature} not yet supported feature for {name} filter.")

    @cached_property
    def info(self) -> FilterInfo:
        try:
            return filter_info(self.name)
            # return list_filters()[self.name] # summary
        except KeyError:
            raise Filter.InvalidName(self.name)

    def __new__(
        self,
        filter_spec: str | fgb.abc.FilterGraphObject,
        *args,
        filter_id: str = None,
        **kwargs,
    ):
        """FFmpeg filter object (immutable)

        :param filter_spec: FFmpeg filter specification. Acceptable formats
            include:

            * ``str`` of a single-chain FFmpeg filter filtergraph expression
                without any labels or the ``'[sws_flags=flags;]'`` clause.
            * ``Filter`` object (returns the same object)
            * ``Chain`` Must be a single-filter chain.
            * ``Graph`` Must be a single-filter graph without any labels or
                ``sws_flags``

        :param filter_id: Optional id string to distinguish multiple instances
            of a same filter.

        FFmpeg filter class arguments can be specified by position and keyword
        arguments.

        Examples
        ^^^^^^^^

        .. code:: python

           import ffmpegio.filtergraph as fgb

           # "scale=w=200:h=100" can be constructed by any of the following:

           fgb.Filter('scale=200:100')
           fgb.Filter('scale=w=200:h=100')
           fgb.Filter('scale', 200, 100)
           fgb.Filter('scale', w=200, h=100)

        """

        # parse if str given
        if isinstance(filter_spec, str):
            name, _args, _kwargs = filter_utils.parse_filter(filter_spec)

            if isinstance(name, tuple):
                name, _filter_id = name
                if filter_id is None:
                    #
                    filter_id = _filter_id
            if len(_args) > 0 or len(_kwargs) > 0:
                if len(args) or len(kwargs):
                    raise fgb.FiltergraphInvalidExpression(
                        "Filter arguments can only be passed via either in a Filter expression or the function arguments"
                    )
                args = _args
                kwargs = _kwargs
            proto = [name, args, kwargs]
        else:
            no_id = filter_id is None
            if isinstance(filter_spec, fgb.Graph):
                if not filter_spec.is_simple_chain() or len(filter_spec[0]) != 1:
                    raise fgb.FiltergraphConversionError(
                        "Cannot convert a multi-filter `Graph` object to a `Filter` object"
                    )
                filter_spec = filter_spec[0][0]
                if no_id:
                    return filter_spec
            elif isinstance(filter_spec, fgb.Chain):
                if len(filter_spec) != 1:
                    raise fgb.FiltergraphConversionError(
                        "Cannot convert a `Chain` or `Graph` object to a `Filter` object if it does not have exactly one filter."
                    )
                filter_spec = filter_spec[0]
            elif not isinstance(filter_spec, fgb.Filter):
                raise ValueError("Invalid filterspec type.")

            proto = [*filter_spec]

            # check id: if matched, no change needed
            if filter_spec.id == filter_id:
                return filter_spec
            elif filter_id is None:
                proto[0] = filter_spec.name
            else:
                proto[0] = (filter_spec.name, filter_id)

        # convert kwargs dict to tuple of tuples of key and values (immutable)
        proto[-1] = tuple(proto[-1].items())

        # create the final tuple
        return tuple.__new__(Filter, proto)

    def copy(self) -> Filter:
        """returns itself (immutable)"""
        return self

    def __iter__(self):
        """iterates to be compatible with compose_filter()"""

        for i, v in enumerate(super().__iter__()):
            yield dict(v) if i == 2 else v

    def __getitem__(self, key):
        """make sure the last

        :param key: _description_
        :return: _description_
        """
        value = tuple.__getitem__(self, key)

        if key in (2, -1):
            value = dict(value)
        elif isinstance(key, slice) and isinstance(value[-1], tuple):
            value = (*value[:-1], dict(value[-1]))
        return value

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
            fgb.Graph(self).compose(show_unconnected_inputs, show_unconnected_outputs)
            if show_unconnected_inputs or show_unconnected_outputs
            else filter_utils.compose_filter(*self)
        )

    def __repr__(self):
        type_ = type(self)
        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{self.compose(True, True)}\"
    Number of inputs: {self.get_num_inputs()}
    Number of outputs: {self.get_num_outputs()}
"""

    @property
    def name(self) -> str:
        name = self[0]
        return name if isinstance(name, str) else name[0]

    @property
    def fullname(self) -> str:
        name = self[0]
        return name if isinstance(name, str) else f"{name[0]}@{name[1]}"

    @property
    def id(self) -> str | None:
        name = self[0]
        return None if isinstance(name, str) else name[1]

    @property
    def ordered_options(self) -> tuple:
        return self[1]

    @property
    def named_options(self) -> dict:
        return dict(self[-1])

    def get_pad_media_type(
        self, port: Literal["input", "output"], pad_id: int
    ) -> Literal["audio", "video"]:
        try:
            port = (
                "inputs"
                if "inputs".startswith(port)
                else "outputs"
                if "outputs".startswith(port)
                else None
            )
            assert port is not None
        except:
            raise ValueError(
                f"{port} is an invalid filter port type. Must be either 'input' or 'output'."
            )

        port_info = getattr(self.info, port)

        if port_info is None:
            # filters with homogeneous multiple in/out
            # fmt:off
            pure_video = {
                "inputs": [
                    "bm3d", "decimate", "fieldmatch", "hstack", "interleave", "mergeplanes",
                    "mix", "premultiply", "signature", "streamselect", "unpremultiply",
                    "vstack", "xmedian", "xstack",
                ],
                "outputs": [
                    "alphaextract", "extractplanes", "select", "split", "streamselect",
                ],
            }
            pure_audio = {
                "inputs": [
                    "afir", "ainterleave", "amerge", "amix", "astreamselect", "headphone", "join", "ladspa",
                ],
                "outputs": [
                    "acrossover", "aselect", "asplit", "astreamselect", "channelsplit",
                ],
            }
            # fmt:on

            if self.name in pure_video[port]:
                return "video"
            if self.name in pure_audio[port]:
                return "audio"

            if self.name == "concat":
                n = self.get_option_value("n")
                v = self.get_option_value("v")
                a = self.get_option_value("a")
                return (
                    ("video" if pad_id % n < v else "audio")
                    if port != "outputs"
                    else ("video" if pad_id < v else "audio")
                )

            # multiple pads possible if streams option set
            if self.name in ("movie", "amovie"):
                val = self.get_option_value("streams")
                if val is None:
                    return "video" if self.name == "movie" else "audio"

                spec = val.split("+")[pad_id]
                return (
                    "video"
                    if spec == "dv"
                    else (
                        "audio"
                        if spec == "da"
                        else {"v": "video", "a": "audio", None: None}[
                            parse_stream_spec(spec).get("media_type", None)
                        ]
                    )
                )

            # 2nd pad for audio visualization stream
            vis_mode = ["afir", "aiir", "anequalizer", "ebur128", "aphasemeter"]
            if port == "outputs" and self.name in vis_mode:
                return "video" if pad_id else "audio"

            raise Filter.Unsupported(self.name, "dynamic media type resolution")

        try:
            pad_info = port_info[pad_id]
            return pad_info["type"]
        except:
            raise ValueError(
                f"{pad_id} is an invalid pad_id as an {port[:-1]} pad of {self.name} filter."
            )

    def get_option_value(self, option_name):

        # first check the named options as-is
        named_opts = self.named_options
        try:
            return named_opts[option_name]
        except:
            pass

        # get the option info
        i, opt_info = next(
            (
                (i, o)
                for i, o in enumerate(self.info.options)
                if o.name == option_name or option_name in o.aliases
            ),
            (None, None),
        )
        if i is None:
            raise Filter.InvalidOption(
                f"Invalid option name ({option_name}) for {self.name} filter"
            )

        try:
            # try full name first
            return named_opts[opt_info.name]
        except:
            # try alias name next
            for a in opt_info.aliases:
                try:
                    return named_opts[a]
                except:
                    pass

            # try from ordered options next
            try:
                return self.ordered_options[i]
            except:
                # if nothing fits, use the default value (maybe undefined/None)
                return opt_info.default

    def get_num_inputs(self):
        """get the number of input pads of the filter
        :return: number of input pads
        :rtype: int
        """
        name = self.name
        if not isinstance(name, str):
            # name@id
            name = name[0]

        nin = self.info.inputs

        if nin is not None:  # fixed number
            return len(nin)

        def _inplace():
            return 1 if self.get_option_value("inplace") else 2

        def _headphone():
            if self.get_option_value("hrir") == "multich":
                return 2
            map = self.get_option_value("map")
            return (
                len(re.split(r"\s*\|\s*", map)) + 1
                if isinstance(map, str)
                else len(map) + 1
            )

        def _mergeplanes():
            map = self.get_option_value("mapping")
            if not isinstance(map, int):
                map = int(map, 16 if map.startswith("0x") else 10)

            return int(max(f"{map:08x}"[::2])) + 1

        def _concat():
            return self.get_option_value("n") * (
                self.get_option_value("v") + self.get_option_value("a")
            )

        def _scale():
            # ref input supported in v7.1 or later
            w_expr = self.get_option_value("w")
            h_expr = self.get_option_value("h")
            return (
                2
                if any(
                    expr.find(key) >= 0
                    for expr in (w_expr, h_expr)
                    for key in ("ref_", "rw", "rh")
                )
                else 1
            )

        option_name, inc = {
            "afir": ("nbirs", 1),
            "concat": (None, _concat),
            "decimate": ("ppsrc", 1),
            "fieldmatch": ("ppsrc", 1),
            "headphone": (None, _headphone),
            "interleave": ("nb_inputs", 0),
            "limitdiff": ("reference", 1),
            "mergeplanes": (None, _mergeplanes),
            "premultiply": (None, _inplace),
            "unpremultiply": (None, _inplace),
            "signature": ("nb_inputs", 0),
            "scale": (None, _scale),
            # "astreamselect": ("inputs", 0),
            # "bm3d": ("inputs", 0),
            # "hstack": ("inputs", 0),
            # "mix": ("inputs", 0),
            # "streamselect": ("inputs", 0),
            # "vstack": ("inputs", 0),
            # "xmedian": ("inputs", 0),
            # "xstack": ("inputs", 0),
        }.get(name, ("inputs", 0))

        return (
            int(self.get_option_value(option_name)) + inc
            if isinstance(option_name, str)
            else inc()
        )

    def get_num_outputs(self):
        """get the number of output pads of the filter
        :return: number of output pads
        :rtype: int
        """
        name = self.name

        nout = self.info.outputs
        if nout is not None:  # arbitrary number allowed
            return len(nout)

        def _concat():
            return int(self.get_option_value("a")) + int(self.get_option_value("v"))

        def _list_var(opt, sep, inc):
            v = self.get_option_value(opt)
            return (
                1
                if v is None
                else (
                    len(v)
                    if sep == r"\|" and not isinstance(v, str)
                    else len(re.split(rf"\s*{sep}\s*", v))
                )
            ) + inc

        def _channelsplit():
            layout = self.get_option_value("channel_layout")
            channels = self.get_option_value("channels")
            return len(
                re.split(
                    r"\s*\+\s*",
                    layouts()["layouts"][layout] if channels == "all" else channels,
                )
            )

        # fmt:off
        option_name, inc = {
            "afir": ("response", 1),  # +video stream
            "aiir": ("response", 1),  # +video stream
            "anequalizer": ("curves", 1),
            "ebur128": ("video", 1),
            "aphasemeter": ("video", 1),
            "acrossover": ('split',partial( _list_var,"split", " ", 1)),  # split option (space-separated)
            "asegment": ("timestamps", partial( _list_var,"timestamps", r"\|", 1)),
            "segment": ("timestamps", partial( _list_var,"timestamps", r"\|", 1)),
            "astreamselect": ("map", partial( _list_var,"map", " ", 0)),  # parse map?
            "streamselect": ("map", partial( _list_var,"map", " ", 0)),  # parse map?
            "extractplanes": ("planes", partial( _list_var,"planes", r"\+", 0)),  # parse planes
            "amovie": ("streams",partial( _list_var,"streams", r"\+", 0)),
            "movie": ("streams",partial( _list_var,"streams", r"\+", 0)),
            "channelsplit": (('channel_layout', 'channels'),_channelsplit),  # parse channel_layout/channels
            "concat": (('a', 'v'), _concat),  # sum a and v
            # "aselect": (("output", "n"), 0),  # must resolve alias...
            # "asplit": ("outputs", 0),
            # "select": (("output", "n"), 0),
            # "split": ("outputs", 0),
        }.get(name, ("outputs", 0))
        # fmt:on

        return (
            int(self.get_option_value(option_name)) + inc
            if isinstance(inc, int)
            else inc()
        )

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
        elif len(index) == 2:
            index = (0, *index)

        if index[-1] < 0:
            numpads = self.get_num_inputs() if input else self.get_num_outputs()
            index = (*index[-3:-1], numpads + index[-1])

        return index

    def get_num_filters(self, chain: int | None = None) -> int:
        """get the number of filters of the specfied chain

        :param chain: id of the chain, defaults to None to get the total number
                      of filters across all chains
        """

        if chain:
            raise ValueError(f"{chain=} is invalid. Filter object only has 1 chain.")
        return 1

    def get_num_chains(self) -> int:
        """get the number of chains"""
        return 1

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

        # must convert to FilterGraph as it's the only object with labels
        fg = fgb.Graph([[self]])
        return fg.add_label(label, inpad, outpad, force)

    def _iter_pads(
        self,
        n: int,
        pad: int | None,
        filter: Literal[0] | None,
        chain: Literal[0] | None,
        exclude_chainable: bool,
        chainable_first: bool,
        chainable_only: bool,
    ) -> Generator[tuple[PAD_INDEX, Filter]]:
        """Iterate over input pads of the filter

        :param n: number of pads
        :param pad: pad id
        :param filter: filter index
        :param chain: chain index
        :param exclude_chainable: True to leave out the last pads
        :param chainable_first: True to yield the last pad first then the rest
        :yield: filter pad index, link label, filter object
        """

        if not n:
            # takes no input, nothing to iterate
            return

        if (isinstance(filter, int) and filter != 0) or (
            isinstance(chain, int) and chain != 0
        ):
            # Filter alone can have no connections so yields no pad
            raise FiltergraphInvalidIndex(f"Invalid {filter=} or {chain=} id")

        if pad is not None:
            if pad < 0:  # resolve negative pad index
                pad += n
            if pad < 0 or pad >= (n - 1 if exclude_chainable else n):
                raise FiltergraphInvalidIndex(f"Invalid {pad=} id")

        if chainable_only:
            if pad is None:
                pad = n - 1

            if pad != n - 1:
                raise FiltergraphInvalidIndex(f"Invalid {pad=} is not chainable pad")

            if not exclude_chainable and pad == n - 1:
                yield (pad,), self, None

        elif pad is None:
            if chainable_first or exclude_chainable:
                n = n - 1
                if chainable_first and not exclude_chainable:
                    yield (n,), self, None
            for j in range(n):
                yield (j,), self, None
        else:
            yield (pad,), self, None

    def iter_input_pads(
        self,
        pad: int | None = None,
        filter: Literal[0] | None = None,
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
    ) -> Generator[tuple[PAD_INDEX, Filter, None]]:
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
        :param full_pad_index: True to return 3-element index
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        for index, filter, other_index in self._iter_pads(
            self.get_num_inputs(),
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            chainable_only,
        ):
            yield (
                ((0, 0, *index), filter, other_index)
                if full_pad_index
                else (index, filter, other_index)
            )

    def iter_output_pads(
        self,
        pad: int | None = None,
        filter: Literal[0] | None = None,
        chain: Literal[0] | None = None,
        *,
        exclude_chainable: bool = False,
        chainable_first: bool = False,
        include_connected: bool = False,
        unlabeled_only: bool = False,
        chainable_only: bool = False,
        full_pad_index: bool = False,
    ) -> Generator[tuple[PAD_INDEX, Filter, PAD_INDEX | None]]:
        """Iterate over output pads of the filter

        :param pad: pad id, defaults to None
        :param filter: filter index, defaults to None
        :param chain: chain index, defaults to None
        :param exclude_chainable: True to leave out the last output pads, defaults to False (all avail pads)
        :param chainable_first: True to yield the last output first then the rest, defaults to False
        :param include_connected: True to include pads connected to output streams, defaults to False
        :param unlabeled_only: True to leave out named outputs, defaults to False to return only all outputs
        :param chainable_only: True to only iterate chainable pads, defaults to False to return all outputs
        :param full_pad_index: True to return 3-element index
        :yield: filter pad index, link label, filter object, output pad index of connected filter if connected
        """

        for index, filter, other_index in self._iter_pads(
            self.get_num_outputs(),
            pad,
            filter,
            chain,
            exclude_chainable,
            chainable_first,
            chainable_only,
        ):
            yield (
                ((0, 0, *index), filter, other_index)
                if full_pad_index
                else (index, filter, other_index)
            )

    def iter_chains(self) -> Generator[fgb.Chain]:
        """iterate over chains of the filtergraphobject

        :yields: chain object
        """

        yield fgb.Chain([self])

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

        :param inplace: Must be ``False`` as the result is always a ``Graph``.
            If ``True``, a ``ValueError` exception will be raised.
        :return: new filtergraph object or ``None`` if ``inplace=True``

        * link labels may be auto-renamed if there is a conflict

        """

        if inplace:
            raise ValueError("Filter object cannot perform connect() with inplace=True")

        return fgb.as_filterchain(self).connect(
            right,
            from_left,
            to_right=to_right,
            from_right=from_right,
            to_left=to_left,
            chain_siso=chain_siso,
            sws_flags_policy=sws_flags_policy,
            inplace=False,
        )

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
        """append another filtergraph object and make downstream connections

        :param left: receiving filtergraph object
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

        :param inplace: Must be ``False`` as the result is always a ``Graph``.
            If ``True``, a ``ValueError` exception will be raised.
        :return: new filtergraph object or ``None`` if ``inplace=True``

        * link labels may be auto-renamed if there is a conflict

        """

        if inplace:
            raise ValueError("Filter object cannot perform connect() with inplace=True")

        return fgb.as_filterchain(self).rconnect(
            left,
            from_left,
            to_right=to_right,
            from_right=from_right,
            to_left=to_left,
            chain_siso=chain_siso,
            sws_flags_policy=sws_flags_policy,
            inplace=False,
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

        if inplace:
            raise ValueError("Filter object cannot perform connect() with inplace=True")

        return fgb.as_filterchain(self).attach(
            right,
            left_on,
            right_on,
            chainable_only=chainable_only,
            chain_siso=chain_siso,
            inplace=False,
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

        if inplace:
            raise ValueError("Filter object cannot perform connect() with inplace=True")

        return fgb.as_filterchain(self).rattach(
            left,
            left_on,
            right_on,
            chainable_only=chainable_only,
            chain_siso=chain_siso,
            inplace=False,
        )

    def apply(self, options: dict, filter_id: str | None = None) -> Filter:
        """apply new filter options

        :param options: new option key-value pairs. For ordered option, use
            positional index (0 corresponds to the first option). Set value as
            ``None`` to drop the option. Ordered options can only be dropped in
            contiguous fashion, including the last ordered option.
        :param filter_id: new filter id, defaults to clear existing filter id
        :return: new filter with modified options

        .. note::

            To add new ordered options, int-keyed options item must be presented in
            the increasing key order so the option can be expanded one at a time.

        """

        name, opts, kwopts = self

        if isinstance(name, tuple):
            name = name[0]
        opts = list(opts)
        nopts = len(opts)

        delopts = set()
        for k, v in options.items():
            if isinstance(k, int):
                if k < 0 or k > nopts:
                    raise Filter.Error(f"invalid positional index [{k}]")
                if v is not None:
                    if k < nopts:
                        opts[k] = v
                    else:
                        opts = [*opts, v]
                        nopts += 1
                elif k < 0 or k > nopts:
                    delopts.add(k)
            else:
                if v is None:
                    del kwopts[k]
                else:
                    kwopts[k] = v

        if len(delopts):
            delopts = sorted(list(delopts))
            o1 = delopts[0] - 1
            on = delopts[-1]
            if on != nopts or len(delopts) != on - o1:
                raise Filter.Error(
                    f"cannot drop specified ordered options {delopts}. They must be contiguous and include the last ordered option."
                )
            opts = opts[:o1]

        return Filter(name, *opts, filter_id=filter_id, **kwopts)

    def _input_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        pad_pos = index[2]
        return pad_pos >= 0 and pad_pos < self.get_num_inputs()

    def _output_pad_is_available(self, index: tuple[int, int, int]) -> bool:
        pad_pos = index[2]
        return pad_pos >= 0 and pad_pos < self.get_num_outputs()

    def _check_partial_pad_index(
        self, index: tuple[int | None, int | None, int | None], is_input: bool
    ) -> bool:
        """True if defined values of the partial pad index are valid"""

        if any(i is not None and i > 0 for i in index[:2]):
            return False

        pad = index[2]
        if pad is None:
            pad = 0  # use the smallest pad id

        n = self.get_num_inputs() if is_input else self.get_num_outputs()
        return pad >= 0 and pad < n

    def _input_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified input pad is chainable"""
        if any(i for i in index[:2]):
            return False
        return index[2] == self.get_num_inputs() - 1

    def _output_pad_is_chainable(self, index: tuple[int, int, int]) -> bool:
        """True if specified output pad is chainable"""
        if any(i for i in index[:2]):
            return False
        return index[2] == self.get_num_outputs() - 1
