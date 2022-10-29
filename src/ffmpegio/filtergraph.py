"""ffmpegio.filtergraph module - FFmpeg filtergraph classes

    Arithmetic Filtergraph Construction
    ===================================

    .. list-table:: Supported Arithmetic Operators
   :widths: 15 10 30
   :header-rows: 1

   ---------------------------------  ------------------------------------------------------------
   Operation                       Description  Related Methods
   ------------------------------  ------------------------------------------------------------
   `+` operator                    Chaining/join operator, supports scalar expansion
   `Filter + Filter -> Chain`      Create a filterchain from 2 filters
   `Chain  + Filter -> Chain`      Append filter to filterchain
   `Filter + Chain  -> Chain`      Prepend filter to filterchain
   `Chain  + Chain  -> Chain`      Concatenate filterchains
   `Filter + Graph  -> Graph`      Prepend filer to first available input of each chain
   `Graph  + Filter -> Graph`      Append filter to first available output of each chain
   `Graph  + Chain  -> Graph`      Append filterchain to first available input of each chain
   `Chain  + Graph  -> Graph`      Prepend filterchain to first available output of each chain
   `Graph  + Graph  -> Graph`      Join 2 graphs by matching their inputs and outputs in order

   `*` operator                    Multiplicate-n-stacking operator
   `Filter * int    -> Graph`      Stacking the filters (int) times
   ` Chain * int    -> Graph`      Stacking the chain (int) times
   ` Graph * int    -> Graph`      Stacking the input graph (int) times
   
   `|` operator                    Stacking operator
   `Filter | Filter -> Graph`      Stacking the filters
   ` Chain | Filter -> Graph`      Stacking chain and filter
   `Filter | Chain  -> Graph`      Stacking filter and chain
   ` Chain | Chain  -> Graph`      Stacking the filterchains
   `Filter | Graph  -> Graph`      Prepend filter as a new chain
   ` Graph | Filter -> Graph`      Appendd filter as a new chain
   ` Graph | Chain  -> Graph`      Stack graph and chain
   ` Chain | Graph  -> Graph`      Stack
   ` Graph | Graph  -> Graph`      Stack filtergraphs

   left `>>` operator              Input labeling or attach input filter/chain
   `      str >> Filter -> Graph`  Label first available input pad*
   `      str >> Chain  -> Graph`  Label first available input pad*
   `      str >> Graph  -> Graph`  Label first available chainable input pad*
   `   Filter >> Graph  -> Graph`  Attach filter output to first available input pad
   `    Chain >> Graph  -> Graph`  Adding Chain to itself int times
   `(_,Index) >> Filter -> Graph`  Specify input pad
   `(_,Index) >> Chain  -> Graph`  Specify input pad of the first filter
   `(_,Index) >> Graph  -> Graph`  Specify input pad
   
   right `>>` operator             Output labeling or attach output filter/chain
   `Filter >> str       -> Graph`  Label first available output pad*
   ` Chain >> str       -> Graph`  Label first available output pad*
   ` Graph >> str       -> Graph`  Label first available chainable output pad*
   ` Graph >> Filter    -> Graph`  Attach filter to the first 
   ` Graph >> Chain     -> Graph`  Adding Chain to itself int times
   `Filter >> (Index,_) -> Graph`  Specify output pad
   ` Chain >> (Index,_) -> Graph`  Specify output pad
   ` Graph >> (Index,_) -> Graph`  Specify output pad
   ------------------------------  ------------------------------------------------------------

Filter Pad Labeling
===================

`str >> Filter/Chain/Graph` and `Filter/Chain/Graph >> str` operations can be used to set input
and output labels, respectively. The labels must be specified in square brackets as in the same
manner as FFmpeg filtergraph specification.

.. code-block::python

    fg = '[in]' >> Filter('scale',0.5,-1) >> '[out]'

The brackets are required to distinguish labels from str expressions of filter, chain, and graph.
For example, the following expression chains `scale` and `setsar` filters:

.. code-block::python

    fg = '[in]' >> Filter('scale',0.5,-1) + 'setsar=1/1' >> '[out]'

Filter Pad Indexing
===================

Both input and output filter pads can be specified in a number of ways:

    ---------------------  -----------------------------------------------------------------------
    Syntax                 Description
    ---------------------  -----------------------------------------------------------------------
    int n                  Specifies the n-th pad of the first available filter
    (int m, int n)         Specifies the n-th pad of the m-th filter of the first available chain
    (int k, int m, int n)  Specifies the n-th pad of the m-th filter of the k-th chain
    str label              Specifies the pad associated with the link label (no bracket necessary)
    ---------------------  -----------------------------------------------------------------------

 Except for the label indexing, which is a Graph specific feature, all the indexing syntax may be
 used by `Filter`, `Chain`, or `Graph` class instances. An irrelevant field (e.g., chain or filter 
 indexing for a `Filter` instance) will be ignored. Standard negative-number indexing is supported.

"""
from collections import UserList, abc
from contextlib import contextmanager
from functools import partial, reduce
from copy import deepcopy
import itertools
from math import floor, log10
import os
import re
from subprocess import PIPE
from tempfile import NamedTemporaryFile

from . import path
from .caps import filters as list_filters, filter_info, layouts
from .utils import filter as filter_utils, is_stream_spec
from .utils.fglinks import GraphLinks
from .errors import FFmpegioError


class FilterOperatorTypeError(TypeError, FFmpegioError):
    def __init__(self, other) -> None:
        super().__init__(
            f"invalid filtergraph operation with an incompatible object of type {type(other)}"
        )


class FiltergraphMismatchError(TypeError, FFmpegioError):
    def __init__(self, n, m) -> None:
        super().__init__(
            f"cannot append mismatched filtergraphs: the first has {n} input "
            f"while the second has {m} outputs available."
        )


class FiltergraphInvalidIndex(TypeError, FFmpegioError):
    pass


def _check_joinable(src, dst):
    n = src.get_num_outputs()
    m = dst.get_num_inputs()
    if not (n and m):
        raise FiltergraphMismatchError(n, m)
    return n == 1 and m == 1


def _is_label(expr):
    return isinstance(expr, str) and re.match(r"\[[^\[\]]+\]$", expr)


class FiltergraphPadNotFoundError(FFmpegioError):
    def __init__(self, type, index) -> None:
        target = (
            f"pad {index}"
            if isinstance(index, tuple)
            else f"label {index}"
            if isinstance(index, str)
            else f"filter {index}"
        )
        super().__init__(f"cannot find {type} pad at {target}")


def as_filter(filter_spec):
    if isinstance(filter_spec, Graph):
        if len(filter_spec) != 1 and len(filter_spec[0]) != 1:
            raise FFmpegioError(
                "Only a Graph object with a single one-element chain can be downconverted to Filter."
            )
        else:
            return filter_spec[0, 0]
    if isinstance(filter_spec, Chain):
        if len(filter_spec) != 1:
            raise FFmpegioError(
                "Only a Chain object with a single element can be downconverted to Filter."
            )
        else:
            return filter_spec[0][0]

    return filter_spec if isinstance(filter_spec, Filter) else Filter(filter_spec)


def as_filterchain(filter_specs, copy=False):
    if isinstance(filter_specs, Graph):
        if len(filter_specs) != 1:
            raise FFmpegioError(
                "Only a Graph object with a single chain can be downconverted to Chain."
            )
        return Chain(filter_specs[0])

    return (
        filter_specs
        if not copy and isinstance(filter_specs, Chain)
        else Chain([filter_specs] if isinstance(filter_specs, Filter) else filter_specs)
    )


def as_filtergraph(filter_specs, copy=False):
    return (
        filter_specs
        if not copy and isinstance(filter_specs, Graph)
        else Graph(filter_specs)
    )


def as_filtergraph_object(filter_specs):
    if isinstance(filter_specs, (Filter, Chain, Graph)):
        return filter_specs

    try:
        assert isinstance(filter_specs, str)
        specs, links, sws_flags = filter_utils.parse_graph(filter_specs)
        n = len(specs)
        if links or sws_flags or n > 1:
            return Graph(specs, links, sws_flags)
        specs = specs[0]
        return Filter(specs[0]) if len(specs) == 1 else Chain(specs)
    except:
        try:
            return as_filter(filter_specs)
        except:
            try:
                return as_filterchain(filter_specs)
            except:
                return as_filtergraph(filter_specs)


def _shift_labels(obj, label_type, args):
    if _is_label(args):
        return obj.add_labels(label_type, args)

    if all(_is_label(arg) for arg in args):
        return obj.add_labels(label_type, args)

    is_dst = label_type == "dst"
    assert len(args) == 2 and _is_label(args[0 if is_dst else 1])
    return obj.add_labels(
        label_type, {obj._resolve_index(is_dst, args[is_dst]): args[not is_dst]}
    )


###################################################################################################

# FILTER TOOLS
class Filter(tuple):
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
            super().__init__(
                f"Filter {name} is not defined in FFmpeg (v{path.FFMPEG_VER}).\n"
            )

    class InvalidOption(Error):
        pass

    class Unsupported(Error):
        def __init__(self, name, feature) -> None:
            super().__init__(f"{feature} not yet supported feature for {name} filter.")

    def __new__(self, filter_spec, *args, filter_id=None, **kwargs):
        """_summary_"""
        proto = []
        if isinstance(filter_spec, Filter):
            if filter_spec.id and filter_id is not None:  # new id
                proto.append((filter_spec.name, filter_id))
                proto.extend(filter_spec[1:])
            else:
                proto.extend(filter_spec)
        else:
            # parse if str given
            if isinstance(filter_spec, str):
                filter_spec = filter_utils.parse_filter(filter_spec)

            if not (isinstance(filter_spec, abc.Sequence) and len(filter_spec)):
                raise ValueError("filter_spec must be a non-empty sequence.")
            name, *opts = filter_spec
            if isinstance(name, str):
                proto.append((name, id) if isinstance(id, str) else name)
            elif not (
                isinstance(name, abc.Sequence)
                and len(name) != 2
                and all((isinstance(i, str) for i in name))
            ):
                raise ValueError(
                    "filter_spec[0] must be a str or 2-element str sequence."
                )
            else:
                # name + id: re-id if id arg given
                proto.append(tuple(name) if filter_id is None else (name[0], filter_id))

            proto.extend(opts)

        # create named options dict
        proto_dict = proto.pop() if isinstance(proto[-1], dict) else {}

        # change ordered options if non-None value is given
        nord = len(proto) - 1  # # of ordered options
        for i, o in enumerate(args[:nord]):
            if o is not None:
                proto[i] = o

        # add additional ordered options if present
        proto.extend(args[nord:])

        # update named options
        if len(kwargs):
            proto_dict.update(kwargs)

        # validate named option keys to be str
        for k in proto_dict:
            if not isinstance(k, str):
                raise ValueError(
                    "All keys of the named option dict must be of type str."
                )

        # add the named option dict to the prototype list
        if len(proto_dict):
            proto.append(proto_dict)

        # create the final tuple
        return tuple.__new__(Filter, proto)

    def _resolve_index(self, is_input, index):
        try:
            if isinstance(index, tuple):
                assert len(index) in (1, 2, 3)
                i = index[-1]
            elif isinstance(index, int):
                i = index
            elif index is None:
                i = -1  # pick the last input (chainable)
            else:
                assert False
            n = self.get_num_inputs() if is_input else self.get_num_outputs()
            if i < 0:
                i = n + i
            assert i >= 0 and i < n
            return i
        except:
            raise FiltergraphPadNotFoundError("input" if is_input else "output", index)

    def __getitem__(self, key):
        value = super().__getitem__(key)

        if isinstance(value, dict):
            value = {**value}
        if isinstance(value, tuple):
            if isinstance(value[-1], dict):
                value = tuple((*value[:-1], {**value[-1]}))
            elif isinstance(value[0], dict):
                value = tuple(({**value[-1]}, *value[1:]))
        return value

    def __str__(self):
        return filter_utils.compose_filter(*self)

    def __repr__(self):
        type_ = type(self)
        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{str(self)}\"
    Number of inputs: {self.get_num_inputs()}
    Number of outputs: {self.get_num_outputs()}
"""

    @property
    def name(self):
        name = self[0]
        return name if isinstance(name, str) else name[0]

    @property
    def fullname(self):
        name = self[0]
        return name if isinstance(name, str) else f"{name[0]}@{name[1]}"

    @property
    def id(self):
        name = self[0]
        return None if isinstance(name, str) else name[1]

    @property
    def ordered_options(self):
        opts = self[1:]
        return opts[:-1] if isinstance(opts[-1], dict) else opts

    @property
    def named_options(self):
        opts = self[-1]
        return opts if isinstance(opts, dict) else {}

    @property
    def info(self):
        try:
            return filter_info(self.name)
        except:
            raise Filter.InvalidName(self.name)

    def get_pad_media_type(self, port, pad_id):
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
                if self.get_option_value("streams") is None:
                    return "video" if self.name == "movie" else "audio"

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

        try:
            nin = list_filters()[name].num_inputs
        except:
            raise Filter.InvalidName(name)
        if nin is not None:  # fixed number
            return nin

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

        try:
            nout = list_filters()[name].num_outputs
        except:
            raise Filter.InvalidName(name)
        if nout is not None:  # arbitrary number allowed
            return nout

        def _concat():
            return int(self.get_option_value("a")) + int(self.get_option_value("v"))

        def _list_var(opt, sep, inc):
            v = self.get_option_value(opt)
            return (
                len(v)
                if sep == r"\|" and not isinstance(v, str)
                else len(re.split(rf"\s*{sep}\s*", v))
            ) + inc

        def _channelsplit():
            layout = self.get_option_value("channel_layout")
            channels = self.get_option_value("channels")
            return len(
                re.split(
                    rf"\s*\+\s*",
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

    def add_labels(self, pad_type, labels):
        """turn into filtergraph and add labels

        :param pad_type: filter pad type
        :type pad_type: 'dst'|'src'
        :param labels: pad label(s) and optionally pad id
        :type labels: str|seq(str)|dict(int:str), optional
        """

        fg = Graph([[self]])
        if labels is not None:
            if isinstance(labels, str):
                fg.add_label(labels, **{pad_type: (0, 0, 0)})
            elif isinstance(labels, dict):
                for pad, label in labels.items():
                    fg.add_label(label, **{pad_type: fg._resolve_index(pad)})
            else:
                for pad, label in enumerate(labels):
                    fg.add_label(label, **{pad_type: (0, 0, pad)})
        return fg

    def apply(self, options, filter_id=None):
        """apply new filter options

        :param options: new option key-value pairs. For ordered option, use positional index (0
                        corresponds to the first option). Set value as None to drop the option.
                        Ordered options can only be dropped in contiguous fashion, including the
                        last ordered option.
        :type options: dict
        :param filter_id: new filter id, defaults to None
        :type filter_id: str, optional
        :return: new filter with modified options
        :rtype: Filter

        .. note::

            To add new ordered options, int-keyed options item must be presented in
            the increasing key order so the option can be expanded one at a time.

        """

        try:
            assert isinstance(self[-1], dict)
            kwopts = dict(self[-1])
            try:
                opts = list(self[1:-1])
            except:
                opts = []
        except:
            kwopts = {}
            try:
                opts = list(self[1:])
            except:
                opts = []

        nopts = len(opts)

        delopts = set()
        for k, v in options.items():
            if type(k) == int:
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

        return Filter(self[0], *opts, filter_id=filter_id, **kwopts)

    def __add__(self, other):
        # join
        try:
            other = as_filter(other)
        except Exception:
            return NotImplemented
        if _check_joinable(self, other):
            # one-to-one -> chain
            return Chain([self, other])
        else:
            # one-to-many or many-to-one -> stack and link
            return Graph([[self], [other]], {0: ((1, 0, 0), (0, 0, 0))})

    def __radd__(self, other):
        # join
        try:
            other = as_filter(other)
        except Exception:
            return NotImplemented
        if _check_joinable(other, self):
            # one-to-one -> chain
            return Chain([other, self])
        else:
            # one-to-many or many-to-one -> stack and link
            return Graph([[other], [self]], {0: ((1, 0, 0), (0, 0, 0))})

    def __mul__(self, __n):
        return Graph([[self]] * __n) if isinstance(__n, int) else NotImplemented

    def __rmul__(self, __n):
        return Graph([[self]] * __n) if isinstance(__n, int) else NotImplemented

    def __or__(self, other):
        # stack

        try:
            other = as_filter(other)
        except:
            return NotImplemented
        return Graph([[self], [other]])

    def __ror__(self, other):
        # stack
        if isinstance(other, int):
            return Graph([[self]] * other)
        try:
            other = as_filter(other)
        except:
            return NotImplemented
        return Graph([[other], [self]])

    def __rshift__(self, other):
        """self >> other | self >> (index, other)"""

        # try labeling first
        try:
            return _shift_labels(self, "src", other)
        except FFmpegioError:
            raise
        except:
            pass

        # resolve the index
        if type(other) == tuple:
            if len(other) > 2:
                index, other_index, other = other
            else:
                index, other = other
                other_index = None
        else:
            index = None
            other_index = None

        index = self._resolve_index(False, index)

        # if other is Filter object, do add operation
        try:
            other = as_filtergraph_object(other)
        except:
            return NotImplemented

        # if not Chain or Graph, use other's >> operator
        if not isinstance(other, Filter):
            return other.__rrshift__((self, index, other_index))

        if other.get_num_inputs() == 0:
            raise FiltergraphMismatchError(self.get_num_outputs(), 0)

        # equivalent to add operation or stack and link
        return (
            self.__add__(other)
            if index + 1 == self.get_num_outputs()
            else Graph([[self], [other]], {0: ((1, 0, 0), (0, 0, index))})
        )

    def __rrshift__(self, other):
        """other >> self, (other, index) >> self : attach input label or filter"""

        # try to label first
        try:
            return _shift_labels(self, "dst", other)
        except FFmpegioError:
            raise
        except:
            pass

        # resolve the index
        if type(other) == tuple:
            if len(other) > 2:
                other, other_index, index = other
            else:
                other, index = other
                other_index = None
        else:
            index = None
            other_index = None

        index = self._resolve_index(True, index)

        # if label
        if _is_label(other):
            if other_index is None:
                return self.add_labels("dst", {index: other})
            else:
                raise FiltergraphInvalidIndex("index cannot be assigned to a label")

        # if other is Filter object, do add operation
        try:
            other = as_filtergraph_object(other)
        except:
            return NotImplemented

        # if not Chain or Graph, use other's >> operator
        if not isinstance(other, Filter):
            return other.__rshift__((other_index, index, self))

        if other.get_num_outputs() == 0:
            raise FiltergraphMismatchError(0, self.get_num_inputs())

        if not index:
            # equivalent to chain/add operation
            return self.__radd__(other)
        else:
            # stack and link
            return Graph([[other], [self]], {0: ((1, 0, index), (0, 0, 0))})


####################################################################################


class Chain(UserList):
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

    def _resolve_index(self, is_input, index):
        try:
            if isinstance(index, tuple):
                assert len(index) in (1, 2, 3)
                i = index[-1]
                try:
                    j = index[-2]
                except:
                    j = None
            else:
                j = None
                i = index if isinstance(index, int) else None

            return next(
                (self.iter_input_pads if is_input else self.iter_output_pads)(
                    filter=j, pad=i
                )
            )[:2]
        except:
            raise FiltergraphPadNotFoundError("input" if is_input else "output", index)

    def __str__(self):
        return filter_utils.compose_graph([self.data])

    def __repr__(self):
        type_ = type(self)
        return f"""<{type_.__module__}.{type_.__qualname__} object at {hex(id(self))}>
    FFmpeg expression: \"{str(self)}\"
    Number of filters: {len(self.data)}
    Input pads ({self.get_num_inputs()}): {', '.join((str(id[:-1]) for id in self.iter_input_pads()))}
    Output pads: ({self.get_num_outputs()}): {', '.join((str(id[:-1]) for id in self.iter_output_pads()))}
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

    def __rshift__(self, other):
        """self >> other | self >> (index, other)  | self >> (index, other_index, other)"""

        # try to label first
        try:
            return _shift_labels(self, "src", other)
        except FFmpegioError:
            raise
        except:
            pass

        if type(other) == tuple:
            if len(other) > 2:
                index, other_index, other = other
            else:
                index, other = other
                other_index = None
        else:
            index = None
            other_index = None

        # resolve the index
        if type(other) == tuple:
            index, other = other
        else:
            index = None

        if not len(self):
            if index is not None:
                raise Chain.Error(
                    "attempting to specify a pad index of an empty chain."
                )
            if _is_label(other):
                raise Chain.Error(
                    "attempting to set a pad label specified to an empty chain."
                )
            return as_filterchain(other, True)

        index = self._resolve_index(False, index)

        # if other is Filter object, do add operation
        try:
            other = as_filtergraph_object(other)
        except:
            return NotImplemented

        if isinstance(other, Graph):
            return other.__rrshift__((self, index, other_index))

        if other.get_num_inputs() == 0:
            raise FiltergraphMismatchError(self.get_num_outputs(), 0)

        # equivalent to add operation or stack and link
        return (
            self.__add__(other)
            if index[1] + 1 == self.get_num_outputs()
            else Graph([self, other], {0: ((1, 0, 0), (0, *index))})
        )

    def __rrshift__(self, other):
        """other >> self, (other, index) >> self : attach input label or filter"""

        # try to label first
        try:
            return _shift_labels(self, "dst", other)
        except FFmpegioError:
            raise
        except:
            pass

        # resolve the index
        if type(other) == tuple:
            if len(other) > 2:
                other, other_index, index = other
            else:
                other, index = other
                other_index = None
        else:
            index = None
            other_index = None

        if not len(self):
            if index is not None:
                raise Chain.Error(
                    "attempting to specify a pad index of an empty chain."
                )
            if _is_label(other):
                raise Chain.Error(
                    "attempting to set a pad label specified to an empty chain."
                )
            return as_filterchain(other, True)

        index = self._resolve_index(True, index)

        # if other is Filter object, do add operation
        try:
            other = as_filtergraph_object(other)
        except:
            return NotImplemented

        if isinstance(other, Graph):
            return other.__rshift__((other_index, index, self))

        if other.get_num_outputs() == 0:
            raise FiltergraphMismatchError(0, self.get_num_inputs())

        if not index:
            # equivalent to chain/add operation
            return self.__radd__(other)
        else:
            # stack and link
            return Graph([other, self], {0: ((1, *index), (0, 0, 0))})

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

    def iter_input_pads(self, filter=None, pad=None):
        """Iterate over input pads of the filters

        :param pad: specify if only interested in pid-th pad of each filter, defaults to None
        :type pad: int, optional
        :yield: filter index, pad index, and filter instance
        :rtype: tuple(int, int, Filter)
        """

        def iter_base(i, f):
            n = f.get_num_inputs()
            if pad is None:
                for j in range(n - 1 if i else n):
                    yield (i, j, f)
            elif pad < (n - 1 if i else n):
                yield (i, pad, f)

        try:
            if filter is None:
                for i, f in enumerate(self.data):
                    for v in iter_base(i, f):
                        yield v
            else:
                if filter < 0:
                    filter += len(self.data)
                for v in iter_base(filter, self.data[filter]):
                    yield v
        except:
            # invalid index
            pass

    def iter_output_pads(self, filter=None, pad=None):
        """Iterate over output pads of the filters

        :param pid: specify if only interested in pid-th pad of each filter, defaults to None
        :type pid: int, optional
        :yield: filter index, pad index, and filter instance
        :rtype: tuple(int, int, Filter)

        Filters are scanned from the end to the front
        """

        imax = len(self.data) - 1

        def iter_base(i, f):
            n = f.get_num_outputs()
            if pad is None:
                for j in range(n if i == imax else n - 1):
                    yield (i, j, f)
            elif pad < (n if i == imax else n - 1):
                yield (i, pad, f)

        try:
            if filter is None:
                for i, f in reversed(tuple(enumerate(self.data))):
                    for v in iter_base(i, f):
                        yield v
            else:
                if filter < 0:
                    filter += len(self.data)
                for v in iter_base(filter, self.data[filter]):
                    yield v
        except:
            pass

    def get_chainable_input_pad(self):
        """get first filter's input pad, which can be chained

        :return: filter position, input pad poisition, and filter object.
                 If the head filter is a source filter, returns None.
        :rtype: tuple(int, int, Filter) | None
        """

        if not len(self):
            return None
        f = self[-1]
        nin = f.get_num_inputs()
        return (0, nin - 1, f) if nin else None

    def get_chainable_output_pad(self):
        """get last filter's output pad, which can be chained

        :return: filter position, output pad poisition, and filter object.
                 If the tail filter is a sink filter, returns None.
        :rtype: tuple(int, int, Filter) | None
        """

        if not len(self):
            return None
        f = self[-1]
        nout = f.get_num_outputs()
        return (len(self) - 1, nout - 1, f) if nout else None

    def get_num_inputs(self):
        return len(list(self.iter_input_pads()))

    def get_num_outputs(self):
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

    def add_labels(self, pad_type, labels):
        """turn into filtergraph and add labels

        :param input_labels: input pad labels keyed by pad index, defaults to None
        :type input_labels: dict(int:str), optional
        :param output_labels: output pad labels keyed by pad index, defaults to None
        :type output_labels: dict(int:str), optional
        """

        fg = Graph([self])
        is_input = pad_type == "dst"
        if isinstance(labels, str):
            pad = fg._resolve_index(is_input, None)
            fg.add_label(labels, **{pad_type: pad})
        elif isinstance(labels, dict):
            for pad, label in labels.items():
                pad = fg._resolve_index(is_input, pad)
                fg.add_label(label, **{pad_type: pad})
        else:
            for pad, label in enumerate(labels):
                pad = fg._resolve_index(is_input, pad)
                fg.add_label(label, **{pad_type: pad})
        return fg


####################################################################################


class Graph(UserList):
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

    def _resolve_index(self, is_input, index):
        # call if index needs to be autocompleted
        try:
            if isinstance(index, str):
                # return the pad index associated with the label
                label = (
                    index[1:-1]
                    if len(index) > 2 and index[0] == "[" and index[-1] == "]"
                    else index
                )
                dsts, src = self._links[label]
                if is_input:  # src=None, dst=not None
                    assert self._links.is_input(label)
                    return next(self._links.iter_dst_ids(dsts))
                else:  # dst=None, src=not None
                    assert self._links.is_output(label)
                    return src

            if isinstance(index, tuple):
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
            else:
                k = None
                j = None
                if isinstance(index, int):
                    i = index
                elif index is None:
                    i = None
                else:
                    assert False

            # if any index is None, pick the first available
            return next(
                (self.iter_input_pads if is_input else self.iter_output_pads)(
                    chain=k, filter=j, pad=i
                )
            )[0]
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

    def __rshift__(self, other):
        """self >> other | self >> (index, other)  | self >> (index, other_index, other)"""

        # try to label first
        try:
            return _shift_labels(self, "src", other)
        except FFmpegioError:
            raise
        except:
            pass

        # resolve the index
        if type(other) == tuple:
            if len(other) > 2:
                index, other_index, other = other
            else:
                index, other = other
                other_index = None
        else:
            index = None
            other_index = None

        if not len(self):
            if index is not None:
                raise Chain.Error(
                    "attempting to specify a filter pad index of an empty chain."
                )
            if _is_label(other):
                raise Chain.Error(
                    "attempting to set a filter pad label specified to an empty chain."
                )
            return as_filtergraph(other, True)

        index = self._resolve_index(False, index)

        # if other is Filter object, do add operation
        try:
            other = as_filtergraph_object(other)
        except:
            return NotImplemented

        return self.attach(other, left_on=index, right_on=other_index)

    def __rrshift__(self, other):
        """other >> self, (other, index) >> self, (other, other_index, index) >> self : attach input label or filter"""

        # try to label first
        try:
            return _shift_labels(self, "dst", other)
        except FFmpegioError:
            raise
        except:
            pass

        # resolve the index
        if type(other) == tuple:
            if len(other) > 2:
                other, other_index, index = other
            else:
                other, index = other
                other_index = None
        else:
            index = None
            other_index = None

        if not len(self):
            if index is not None:
                raise Chain.Error(
                    "attempting to specify a filter pad index of an empty chain."
                )
            if _is_label(other):
                raise Chain.Error(
                    "attempting to set a filter pad label specified to an empty chain."
                )
            return as_filtergraph(other, True)

        index = self._resolve_index(True, index)

        # if other is Filter object, do add operation
        try:
            other = as_filtergraph(other)
        except:
            return NotImplemented

        # equivalent to add operation or stack and link
        return other.attach(self, other_index, right_on=index)

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
            label = links.find_dst_label(index)  # get link label if exists
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

    def iter_input_pads(
        self,
        exclude_named=False,
        include_connected=False,
        chain=None,
        filter=None,
        pad=None,
    ):
        """Iterate over filtergraph's filter output pads

        :param exclude_named: True to leave out named inputs, defaults to False to return only all inputs
        :type exclude_named: bool, optional
        :param include_connected: True to include pads connected to input streams, defaults to False
        :type include_connected: bool, optional
        :yield: filter pad index, link label, & source filter object
        :rtype: tuple(tuple(int,int,int), label, Filter)
        """

        def iter_pads():
            try:
                if chain is None:
                    for cid, obj in enumerate(self.data):
                        for j, i, f in obj.iter_input_pads(filter=filter, pad=pad):
                            yield (cid, j, i), f
                else:
                    cid = chain + len(self.data) if chain < 0 else chain
                    for j, i, f in self.data[cid].iter_input_pads(
                        filter=filter, pad=pad
                    ):
                        yield (cid, j, i), f
            except:
                pass

        return self._screen_input_pads(iter_pads, exclude_named, include_connected)

    def iter_chainable_input_pads(
        self, exclude_named=False, include_connected=False, chain=None
    ):
        """Iterate over filtergraph's chainable filter output pads

        :param exclude_named: True to leave out named input pads, defaults to False (all avail pads)
        :type exclude_named: bool, optional
        :param include_connected: True to include input streams, which are already connected to input streams, defaults to False
        :type include_connected: bool, optional
        :yield: filter pad index, link label, & source filter object
        :rtype: tuple(tuple(int,int,int), label, Filter)
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

    def _screen_output_pads(self, iter_pads, exclude_named):
        links = self._links
        for index, f in iter_pads():  # for each output pad
            labels = links.find_src_labels(index)  # get link label if exists
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

    def iter_output_pads(self, exclude_named=False, chain=None, filter=None, pad=None):
        """Iterate over filtergraph's filter output pads

        :param exclude_named: True to leave out named outputs, defaults to False
        :type exclude_named: bool, optional
        :yield: filter pad index,  link label, and source filter object
        :rtype: tuple(tuple(int,int,int), str, Filter)
        """

        def iter_pads():
            try:
                # iterate over all input pads
                if chain is None:
                    for cid, obj in enumerate(self.data):
                        for j, i, f in obj.iter_output_pads(filter=filter, pad=pad):
                            yield (cid, j, i), f
                else:
                    cid = chain + len(self.data) if chain < 0 else chain
                    for j, i, f in self.data[cid].iter_output_pads(
                        filter=filter, pad=pad
                    ):
                        yield (cid, j, i), f
            except:
                pass

        return self._screen_output_pads(iter_pads, exclude_named)

    def iter_chainable_output_pads(self, exclude_named=False, chain=None):
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

    def validate_input_index(self, dst):
        try:
            GraphLinks.validate_pad_id_pair((dst, None))
            for index in GraphLinks.iter_dst_ids(dst):
                self[index[0]].validate_input_index(*index[1:])
        except:
            raise Graph.InvalidFilterPadId("input", dst)

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
            dst = index
            label = self._links.find_dst_label(index)
            desc = f"input pad {index}"

            if label is not None and self._links[label][1] is not None:
                raise Graph.Error(f"{desc} is not an input label.")

        else:
            # given label
            desc = f"link label [{index}]"
            try:
                dsts, src = self._links[index]
            except:
                raise Graph.Error(f"{desc} does not exist.")

            if src is not None:
                raise Graph.Error(f"{desc} is not an input label.")

            dsts = [d for d in self._links.iter_dst_ids(dsts)]
            n = len(dsts)

            if not n:
                raise Graph.Error(
                    f"no input pad found. specified {desc} is an output label."
                )

            if n > 1:
                raise Graph.Error(f"{desc} is associated with multiple input pads.")

            dst = dsts[0]
            label = index

        if label is not None and is_stream_spec(label, True):
            raise Graph.Error(f"{desc} is already connected to an input stream.")

        # make sure the input pad is valid one on the fg (raises if fails)
        self.validate_input_index(dst)

        return dst, label

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
                src = self._links[index][1]
                assert src is not None
            except:
                raise Graph.Error(f"{desc} does not exist, or it is an input label.")
            label = index
        else:
            # given pad index
            desc = f"output pad {index}"
            src = index
            label = None
            labels = self._links.find_src_labels(src)

            # if labels found, only 1 must be an output
            if len(labels):
                labels = [label for label in labels if not self._links.is_linked(label)]
                if len(labels) != 1:
                    raise Graph.Error(
                        f"{desc} is already labeled but associated to no ouput label or multiple output labels"
                    )
                label = labels[0]

        # make sure the output pad is valid (raises if fails)
        self.validate_output_index(src)

        return src, label

    def copy(self):
        return Graph(self)

    def are_linked(self, dst, src):

        self._links.are_linked(dst, src)

    def unlink(self, label=None, dst=None, src=None):
        """unlink specified links

        :param label: specify all the links with this label, defaults to None
        :type label: str|int, optional
        :param dst: specify the link with this dst pad, defaults to None
        :type dst: tuple(int,int,int), optional
        :param src: specify all the links with this src pad, defaults to None
        :type src: tuple(int,int,int), optional
        """
        self._links.unlink(label, dst, src)

    def link(self, dst, src, label=None, preserve_src_label=False, force=False):
        """set a filtergraph link

        :param dst: input pad ids
        :type dst: tuple(int,int,int)
        :param src: output pad index
        :type src: tuple(int,int,int)
        :param label: desired label name, defaults to None (=reuse dst/src label or unnamed link)
        :type label: str, optional
        :param preserve_src_label: True to keep existing output labels of src, defaults to False
                                   to remove one output label of the src
        :type preserve_src_label: bool, optional
        :param force: True to drop conflicting existing link, defaults to False
        :type force: bool, optional
        :return: assigned label of the created link. Unnamed links gets a
                 unique integer value assigned to it.
        :rtype: str|int

        ..notes:

            - Unless `force=True`, dst pad must not be already connected
            - User-supplied label name is a suggested name, and the function could
              modify the name to maintain integrity.
            - If dst or src were previously named, their names will be dropped
              unless one matches the user-supplied label.
            - No guarantee on consistency of the link label (both named and unnamed)
              during the life of the object

        """

        if label is not None:
            GraphLinks.validate_label(label, named_only=True, no_stream_spec=True)
        if dst is not None:
            dst = self._resolve_index(True, dst)
            try:
                f = self.data[dst[0]][dst[1]]
                assert dst[2] >= 0 and dst[2] < f.get_num_inputs()
            except:
                raise Graph.InvalidFilterPadId("input", dst)
        if src is not None:
            src = self._resolve_index(False, src)
            try:
                f = self.data[src[0]][src[1]]
                assert src[2] >= 0 and src[2] < f.get_num_outputs()
            except:
                raise Graph.InvalidFilterPadId("output", src)

        return self._links.link(dst, src, label, preserve_src_label, force)

    def add_label(self, label, dst=None, src=None, force=None):
        """label a filter pad

        :param label: name of the new label. Square brackets are optional.
        :type label: str
        :param dst: input filter pad index or a sequence of pads, defaults to None
        :type dst: tuple(int,int,int) | seq(tuple(int,int,int)), optional
        :param src: output filter pad index, defaults to None
        :type src: tuple(int,int,int), optional
        :param force: True to delete existing labels, defaults to None
        :type force: bool, optional
        :return: actual label name
        :rtype: str

        Only one of dst and src argument must be given.

        If given label already exists, no new label will be created.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        if label[0] == "[" and label[-1] == "]":
            label = label[1:-1]

        GraphLinks.validate_label(
            label, named_only=True, no_stream_spec=src is not None
        )
        if dst is not None:
            GraphLinks.validate_pad_id_pair((dst, None))
            for d in GraphLinks.iter_dst_ids(dst):
                try:
                    f = self.data[d[0]][d[1]]
                    n = f.get_num_inputs()
                    assert d[2] >= 0 and d[2] < (n - 1 if d[1] > 0 else n)
                except:
                    raise Graph.InvalidFilterPadId("input", d)
        elif src is not None:
            GraphLinks.validate_pad_id(src)
            try:
                f = self.data[src[0]][src[1]]
                assert src[2] >= 0 and src[2] < f.get_num_outputs()
            except:
                raise Graph.InvalidFilterPadId("output", src)
        else:
            raise Graph.Error("filter pad index is not given")

        return self._links.create_label(label, dst, src, force)

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

        # analyze the links to get a list of srcs which are connected to multiple dst's/labels
        srcs_info = self._links.get_repeated_src_info()
        if not len(srcs_info):
            return self  # if none found, good to go as is

        # retrieve all the output pads of the filterchains
        chainable_outputs = [v[0] for v in self.iter_chainable_output_pads()]

        # create a clone to modify and output
        fg = Graph(self)

        # process each multi-destination src
        for src, dsts in srcs_info.items():

            # resolve stream media type
            try:
                media_type = fg[src[:2]].get_pad_media_type("o", src[2])
            except Filter.Unsupported as e:
                # if source filter pad media type cannot be resolved, try destination pads
                for dst in dsts.values():
                    if isinstance(dst, tuple):
                        try:
                            media_type = fg[dst[:2]].get_pad_media_type("i", dst[2])
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

            # find `split` filter can be inserted to the src chain
            if src in chainable_outputs:
                # if it can, extend the chain
                fg[src[0]].append(split_filter)
                new_src = (src[0], src[1] + 1)
            else:
                # if not, append a new chain
                fg.append([split_filter])
                new_src = (len(fg) - 1, 0)
                # create a new link from src to split input
                fg._links.link(src, (*new_src, 0), force=True)

            # relink to dst pad and label
            for pid, (label, index) in enumerate(dsts.items()):
                if isinstance(index, str):  # to output label
                    fg._links.add_label(label, dst=(*new_src, pid), force=True)
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
        srcs_info = [self._resolve_index(False, index) for index in from_left]
        nout = len(srcs_info)
        if nout != len(set(srcs_info)):
            raise ValueError(f"from_left pad indices are not unique.")

        dsts_info = [right._resolve_index(True, index) for index in to_right]
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

        for (dst, dst_label), (src, src_label) in zip(dsts_info, srcs_info):
            new_dst = (dst[0] + n0, *dst[1:])

            do_chain = (
                chain_siso
                and self.data[src[0]][src[1]].get_num_outputs() == 1
                and right.data[dst[0]][dst[1]].get_num_inputs() == 1
            )

            if do_chain:
                if dst_label is not None:
                    right._links.remove_label(dst_label, dst)
                chain_pairs.append((new_dst, src, src_label))
                rm_chains.add(new_dst[0])
            else:
                # reuse the src or dst label if given
                link_pairs.append((new_dst, src, src_label or dst_label))

        # stack 2 filtergraphs
        fg = self.stack(right, False, replace_sws_flags)

        if nout > 0:
            # link marked chains
            for link_args in link_pairs:
                fg._links.link(*link_args)

            # combine chainable chains
            for (dst, src, src_label) in reversed(
                sorted(chain_pairs, key=lambda v: v[1])
            ):
                fc_src = fg[src[0]]
                n_src = len(fc_src)
                fc_src.extend(fg.pop(dst[0]))
                if src_label is not None:
                    fg._links.remove_label(src_label)
                fg._links.merge_chains(dst[0], src[0], n_src)
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
        right_on = right._resolve_index(True, right_on)
        left_on = self._resolve_index(False, left_on)
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
        left_on = left._resolve_index(False, left_on)
        right_on = self._resolve_index(True, right_on)
        return left.connect(self, [left_on], [right_on], chain_siso=True)

    def add_labels(self, pad_type, labels):
        """turn into filtergraph and add labels

        :param input_labels: input pad labels keyed by pad index, defaults to None
        :type input_labels: dict(int:str), optional
        :param output_labels: output pad labels keyed by pad index, defaults to None
        :type output_labels: dict(int:str), optional
        """

        fg = Graph(self)
        is_input = pad_type == "dst"
        if isinstance(labels, str):
            pad = fg._resolve_index(is_input, None)
            fg.add_label(labels, **{pad_type: pad})
        elif isinstance(labels, dict):
            for pad, label in labels.items():
                pad = fg._resolve_index(is_input, None)
                fg.add_label(label, **{pad_type: pad})
        else:
            pads = list(
                itertools.islice(
                    fg.iter_input_pads(exclude_named=True)
                    if pad_type == "dst"
                    else fg.iter_output_pads(exclude_named=True),
                    len(labels),
                )
            )
            for label, pad in zip(labels, pads):
                fg.add_label(label, **{pad_type: pad[0]})
        return fg

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


# dict: stores filter construction functions
_filters = {}


def __getattr__(name):
    func = _filters.get(name, None)
    if func is None:
        try:
            notfound = name not in list_filters()
        except path.FFmpegNotFound:
            notfound = True

        if notfound:
            raise AttributeError(
                f"{name} is neither a valid ffmpegio.filtergraph module's instance attribute "
                "nor a valid FFmpeg filter name."
            )

        def func(*args, filter_id=None, **kwargs):
            return Filter(name, *args, filter_id=filter_id, **kwargs)

        func.__name__ = name
        func.__doc__ = path.ffmpeg(
            f"-hide_banner -h filter={name}", universal_newlines=True, stdout=PIPE
        ).stdout
        _filters[name] = func

    return func
