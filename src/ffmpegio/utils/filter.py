from collections.abc import Sequence
import re, itertools, inspect, logging
from .. import utils
from copy import deepcopy


# various regexp objects used in the module
_re_name_id = re.compile(r"\s*([a-zA-Z0-9_]+)(?:\s*@\s*([a-zA-Z0-9_]+))?\s*(=)?")
_re_labels = re.compile(r"\s*\[\s*(.+?)\s*\]")
_re_graph = re.compile(r"(?<!\\)(?:\\\\)*('|;|,|\[)|$")
_re_esc2 = re.compile(r"([\\\'\[\];,])")
_re_quote = re.compile(r"(?<!\\)(?:\\\\)*\'")
_re_args = re.compile(r"\s*(?<!\\)(?:\\\\)*\:\s*")
_re_esc = re.compile(r"\\(.)")
_re_args_kw = re.compile(r"\s*([a-zA-Z0-9_]+)\s*=\s*(.+)\s*")


def parse_filter_args(expr):
    """parse filter argument string

    :param expr: filter argument string
    :type expr: str
    :return: list of argument strings; last element may be a dict of key-value pairs
    :rtype: list of str + dict
    """
    arg_iter = (s for s in _re_quote.split(expr))
    all_args = [""]

    def conv_val(s):
        try:
            return int(s)
        except:
            try:
                return float(s)
            except:
                return s

    while True:
        s = next(arg_iter, None)
        if s is None:
            break
        ss = _re_args.split(s)
        all_args[-1] += ss[0]
        all_args.extend(_re_esc.sub(r"\1", a) for a in ss[1:])
        s = next(arg_iter, None)
        if s is None:
            break
        all_args[-1] += s

    ikw = next(
        (i for i, arg in enumerate(all_args) if _re_args_kw.match(arg)),
        None,
    )

    args = [conv_val(s.rstrip()) for s in (all_args if ikw is None else all_args[:ikw])]

    if ikw is not None:

        def get_kw(arg):
            m = _re_args_kw.match(arg)
            return m[1], conv_val(m[2].rstrip())

        kwargs = {k: v for k, v in (get_kw(arg) for arg in all_args[ikw:])}
        args = [*args, kwargs]
    return args


def compose_filter_args(*args):
    """compose once-escaped filter argument string

    :param *args: list of argument strings; last element may be a dict of key-value pairs
    :type *args: list of str + dict
    :return: filter argument string
    :rtype: str
    """

    def finalize_option_value(value):
        # flatten a sequence and add escaping to ' and \
        # A first level escaping affects the content of each filter option value, which may contain
        # the special character : used to separate values, or one of the escaping characters \'.
        if not isinstance(value, str) and isinstance(value, Sequence):
            value = "|".join(str(value))
        elif isinstance(value, bool):
            value = str(value).lower()  # true|false
        else:
            value = str(value)

        # use quote if value start or ends with space
        s = re.sub(r"([':\\])", r"\\\1", value)
        m = re.match(r"^(\s+)", s)
        if m:
            i = m.end()
            "\\" + "\\".join(*s[:i]) + s[i:]
        m = re.match(r"(\s+)$", s)
        if m:
            i = m.start()
            s = s[i:] + "\\" + "\\".join(*s[i:])

        return s

    kwargs = args[-1] if len(args) > 0 and isinstance(args[-1], dict) else None
    if kwargs is not None:
        args = args[:-1]

    args = ":".join([finalize_option_value(i) for i in args])
    if kwargs:
        kwargs = ":".join(
            [f"{k}={finalize_option_value(v)}" for k, v in kwargs.items()]
        )
        args = ":".join([args, kwargs]) if args else kwargs
    return args


###################################################################################################


def parse_filter(expr):
    """Parse FFmpeg filter expression

    :param expr: filter expression, escaped special characters once
    :type expr: str
    :return: filter name followed by arguments, followed by a dict containing id string
             (empty if id not given)
    :rtype: tuple(str, *args, {['id':str]})
    """

    i = 0

    m = _re_name_id.match(expr, i)
    name = m[1]
    id = m[2]
    i = m.end()

    args = parse_filter_args(expr[i:]) if m[3] else []

    return (((name, id) if id else name), *args)


def compose_filter(name, *args):
    """Compose FFmpeg filter expression

    :param name: filter name, optionally seq of name & id
    :type name: str or (str, str)
    :param args: option value sequence
    :type args: seq of stringifyable items + last item may be a dict to hold
                key-value pairs
    :return: filter expression, once escaped
    :rtype: str
    """

    expr = name if isinstance(name, str) else f"{name[0]}@{name[1]}"

    if len(args):
        expr = f"{expr}={compose_filter_args(*args)}"

    return expr


###################################################################################################


def parse_graph(expr):
    """parse filter graph expression

    :param expr: twice-escaped filter graph string
    :type expr: str
    :return: tuple of unescaped filter graph blob, input labels, output labels, chain links, and sws_flags list
    :rtype: (list of list of (name, args, id), dict, dict, dict, list)

    Note
    ----

    - labels of the links connecting the filter chains are dropped

    """

    labels = {}
    # key=pad label; value=[tuple(chain,filter,pad)|None,tuple(chain,filter,pad)|None]

    def add_pad(label, output, *ids):
        sig = labels.get(label, None)
        if sig is None:
            labels[label] = [None, ids] if output else [ids, None]
        else:
            if sig[output] is None:
                sig[output] = ids
            else:
                raise ValueError(
                    f'Filter graph specifies multiple \'{label}\' {"output" if output else "input"} pads.'
                )

    def parse_labels(expr, i, output, *fid):
        m = _re_labels.match(expr, i)
        p = 0
        while m:
            add_pad(m[1], output, *fid, p)
            i = m.end()
            p += 1
            m = _re_labels.match(expr, i)

        return i

    n = len(expr)

    # get scale flags if given
    m = re.match(r"\s*sws_flags=(.+);", expr)
    if m:
        sws_flags = parse_filter_args(m[1])
        i = m.end()
    else:
        sws_flags = None
        i = 0  # string position

    fg = []
    fc = []
    cid = 0  # current chain id
    fid = 0  # current filter id in chain <cid>
    fs = ""
    while i < n:
        m = _re_graph.search(expr, i)
        ch = m[1]
        j = m.end()

        s = re.sub(r"\\(.)", r"\1", expr[i : j - 1] if ch else expr[i:])
        if s and not s.isspace():
            fs += s

        if ch == "[":  # input/output labels
            i = parse_labels(expr, j - 1, bool(fs), cid, fid)  # grab all labels
            if i == n:
                # add new filter to the chain
                fc.append(parse_filter(fs))

                # if new chain, add it to the graph
                if not fid:
                    fg.append(fc)

        else:
            i = j

            if ch == "'":
                # add quoted text to fs unchanged
                j = expr.find("'", i) + 1
                if j <= 0:
                    raise ValueError(
                        "a quote in the filter graph string not terminated properly"
                    )
                fs += expr[i - 1 : j]
                i = j

            else:

                # add new filter to the chain
                fc.append(parse_filter(fs))

                # if new chain, add it to the graph
                if not fid:
                    fg.append(fc)

                # update the id's for the next filter element
                if ch == ";":
                    cid += 1
                    fc = []
                    fid = 0
                else:
                    fid += 1
                fs = ""

    # get input/output pads that requires streams
    input_labels = {}
    output_labels = {}
    links = {}

    for label, (inp, outp) in labels.items():
        if outp is None:
            input_labels[label] = inp
        elif inp is None:
            output_labels[label] = outp
        else:
            links[inp] = outp

    return (
        fg,
        input_labels,
        output_labels,
        links,
        sws_flags,
    )


def compose_graph(
    filter_specs, input_labels=None, output_labels=None, links=None, sws_flags=None
):
    """Compose complex filter graph
    :param filter_specs: a nested sequence of argument sequences to compose_filter() to define
               a filter graph. The last element of each filter argument sequence
               may be a dict, defining its keyword arguments.
    :type filter_specs: seq(seq(filter_args))
    :param input_labels: specifies labels of filter input pads which receives
                         input streams. Keys are the link labels and values
                         are sequences of (chain_id, filter_id, in_pad_id),
                         chain_id and filter_id are ints, specifying the filter
                         index in fg, and in_pad_id is an int specifying the
                         input pad, defaults to None
    :type input_labels: dict, optional
    :param output_labels: specifies labels of filter output pads which connect
                         to output streams. Keys are the link labels and values
                         are sequences of (chain_id, filter_id, out_pad_id),
                         chain_id and filter_id are ints, specifying the filter
                         index in fg, and out_pad_id is an int specifying the
                         output pad, defaults to None
    :type output_labels: dict, optional
    :param links: specifies inter-chain links. Key is a tuple of
                  (chain_id, filter_id, in_pad_id) defining the input pad
                  and value of a tuple of (chain_id, filter_id, out_pad_id)
                  defining the output pad, defaults to None
    :type links: dict, optional
    :param sws_flags: specify swscale flags for those automatically inserted
                      scalers, defaults to None
    :type sws_flags: seq of stringifyable elements with optional dict as the last
                     element for the keyword flags, optional
    :returns: filter graph expression
    :rtype: str

    Note
    ----

    - All the pad_ids are used to sort the assigned labels and NOT the absolute
      pad index. The lowest pad_id is assigned to the first pad and the highest
      pad_id is assigned tot he last pad, regardless of their id value


    Examples
    --------

    Here is the "Multiple input overlay in 2x2 grid" example in
    https://trac.ffmpeg.org/wiki/FilteringGuide:

    ```
        [1:v]negate[a]; \\
        [2:v]hflip[b]; \\
        [3:v]edgedetect[c]; \\
        [0:v][a]hstack=inputs=2[top]; \\
        [b][c]hstack=inputs=2[bottom]; \\
        [top][bottom]vstack=inputs=2[out]
    ```

    This filtergraph can be composed by the following Python script:

    ```python
        fg = [
            [("negate",)], # chain #0
            [("hflip",)],  # chain #1
            [("edgedetect",)], # chain #2
            [("hstack", {"inputs": 2})], # chain #3
            [("hstack", {"inputs": 2})], # chain #4
            [("vstack", {"inputs": 2})], # chain #5
        ]

        input_labels = {
            "1:v": (0, 0, 0), # feeds to negate
            "2:v": (1, 0, 0), # feeds to hflip
            "3:v": (2, 0, 0), # feeds to edgedetect
            "0:v": (3, 0, 0), # feeds to the 1st input of 1st hstack
        }

        output_labels = {"out": (5, 0, 0)} # feeds from vstack output

        links = { # input: output
            (3, 0, 1): (0, 0, 0), # 1st hstack gets its 2nd input from negate
            (4, 0, 0): (1, 0, 0), # 2nd hstack gets its 1st input from hflip
            (4, 0, 1): (2, 0, 0), # 2nd hstack gets its 2nd input from edgedetect
            (5, 0, 0): (3, 0, 0), # vstack gets its 1st input from 1st hstack
            (5, 0, 1): (4, 0, 0), # vstack gets its 2nd input from 2nd hstack
        }

        compose(fg, input_labels, output_labels, links)

    ```

    Note that this filtergraph can be written with a fewer chains using
    side-injections:

    ```
        [2:v]hflip[b]; \\ 
        [1:v]negate, [0:v]hstack=inputs=2[top]; \\ 
        [3:v]edgedetect, [b]hstack=inputs=2, [top]vstack=inputs=2[out]
    ```

    This version can be composed by

    ```python
        fg = [
            [("hflip",)], # chain 0
            [("negate",), ("hstack",{"inputs": 2})], # chain 1
            [("edgedetect",), ("hstack",{"inputs": 2}), ("vstack", {"inputs": 2})], # chain 2
        ]

        input_labels = {
            "1:v": (1, 0, 0), # feeds to negate
            "2:v": (0, 0, 0), # feeds to hflip
            "3:v": (2, 0, 0), # feeds to edgedetect
            "0:v": (1, 1, 0), # feeds to 1st input of hstack in chain 1
        }

        output_labels = {"out": (2, 0, 0)} # feeds from chain 2

        links = { # input: output
            (2, 1, 0): (0, 0, 0), # chain 0 output feeds to 1st input of hstack in chain 1
            (2, 2, 0): (1, 0, 0), # chain 1 output feeds to 1st input of vstack in chain 2
        }

        compose(fg, input_labels, output_labels, links)

    """

    def escape(expr):
        return "'".join(
            [
                si if i % 2 else _re_esc2.sub(r"\\\1", si)
                for i, si in enumerate(_re_quote.split(expr))
            ]
        )

    def define_filter(info, in_labels, out_labels):
        expr = (
            "".join([f"[{in_labels[pad]}]" for pad in sorted(in_labels)])
            if in_labels is not None
            else ""
        )

        if isinstance(info, str):
            s = info
        else:
            s = compose_filter(*info)
        expr += escape(s)
        if out_labels is not None:
            expr += "".join([f"[{out_labels[pad]}]" for pad in sorted(out_labels)])

        return expr

    def assign_link(d, label, cid, fid, pid):
        key = (cid, fid)
        l = d.get(key, None)
        if l is None:
            d[key] = {pid: label}
        elif pid is None:
            l[pid].append(label)
        else:
            l[pid] = label

    # list labels per input pad and per output pad
    in_labels = {}  # labeled input pads
    out_labels = {}  # labeled input pads
    labels = set()  # collection of all the labels
    if input_labels is not None:
        labels = set(input_labels.keys())
        for label, id in input_labels.items():
            assign_link(in_labels, label, *id)

    if output_labels is not None:
        labels |= set(output_labels.keys())
        for label, id in output_labels.items():
            assign_link(out_labels, label, *id)

    if links is not None:

        def set_link_label(i):
            for j in itertools.count():
                label = f"L{j*n+i}"
                if label not in labels:
                    labels.add(label)
                    return label

        for n, (i, o) in enumerate(links.items()):
            label = set_link_label(n)
            assign_link(in_labels, label, *i)
            assign_link(out_labels, label, *o)

    # COMPOSE FILTER GRAPH

    # add optional auto-scaling filter arguments
    expr = (
        ""
        if sws_flags is None
        else f"sws_flags={escape(compose_filter_args(*sws_flags))};"
    )

    # form individual filters, form chains, then comine them into graphs
    expr += ";".join(
        [
            ",".join(
                [
                    define_filter(
                        info, in_labels.get((i, j), None), out_labels.get((i, j), None)
                    )
                    for j, info in enumerate(chains)
                ]
            )
            for i, chains in enumerate(filter_specs)
        ]
    )

    return expr


def check_audio_source(name, args, kwargs):
    poskey = {"aevalsrc": 2, "anoisesrc": 2, "sine": 3}
    try:
        pos = poskey[name]
    except:
        raise ValueError(f"{name} is not one of supported audio source filters")
    try:
        d = args[pos]
    except:
        try:
            d = kwargs["duration"]
        except:
            d = kwargs.get("d", None)
    if d is None or utils.parse_time_duration(d) < 0:
        raise ValueError(
            "Audio source filter must provide finite-valued duration option"
        )

    poskey, short_name, default_rate = {
        "aevalsrc": (4, "s", 44100),
        "anoisesrc": (0, "r", 48000),
        "sine": (2, "r", 44100),
    }[name]
    try:
        ar = args[pos]
    except:
        try:
            ar = kwargs["sample_rate"]
        except:
            ar = kwargs.get(short_name, default_rate)

    poskey, short_name, default_rate = {
        "aevalsrc": (4, "s", 44100),
        "anoisesrc": (0, "r", 48000),
        "sine": (2, "r", 44100),
    }[name]
    try:
        ar = args[pos]
    except:
        try:
            ar = kwargs["sample_rate"]
        except:
            ar = kwargs.get(short_name, default_rate)

    if name == "aevalsrc":
        try:
            exprs = args[0]
        except:
            exprs = kwargs.get("exprs", "")
        ac = exprs.count("|") + 1
    else:
        ac = 1

    return ar, ac


def check_video_source(name, args, kwargs):

    poskey = {
        "cellauto": None,  # default size condition
        "gradients": 6,
        "mandelbrot": None,
        "mptestsrc": 1,
        "frei0r_src": None,
        "life": None,
        "allrgb": 4,
        "allyuv": 4,
        "color": 4,
        "colorspectrum": 4,
        "haldclutsrc": 4,
        "pal75bars": 4,
        "pal100bars": 4,
        "rgbtestsrc": 4,
        "smptebars": 4,
        "smptehdbars": 4,
        "testsrc": 4,
        "testsrc2": 4,
        "yuvtestsrc": 4,
        "sierpinski": None,
    }
    try:
        pos = poskey[name]
    except:
        raise ValueError(f"{name} is not one of supported video source filters")
    if pos is not None:
        try:
            d = args[pos]
        except:
            try:
                d = kwargs["duration"]
            except:
                d = kwargs.get("d", None)
        if d is None or utils.parse_time_duration(d) < 0:
            raise ValueError(
                "Video source filter must provide finite-valued duration option"
            )

    poskey = {
        "cellauto": (6, [320, 518]),  # default size condition
        "gradients": (0, [640, 480]),
        "mandelbrot": (7, [640, 480]),
        "mptestsrc": (None, [256, 256]),
        "frei0r_src": (0, None),
        "life": (5, [320, 240]),
        "allrgb": (None, [4096, 4096]),
        "allyuv": (None, [4096, 4096]),
        "color": (2, [320, 240]),
        "colorspectrum": (2, [320, 240]),
        "haldclutsrc": (None, None),
        "pal75bars": (2, [320, 240]),
        "pal100bars": (2, [320, 240]),
        "rgbtestsrc": (2, [320, 240]),
        "smptebars": (2, [320, 240]),
        "smptehdbars": (2, [320, 240]),
        "testsrc": (2, [320, 240]),
        "testsrc2": (2, [320, 240]),
        "yuvtestsrc": (2, [320, 240]),
        "sierpinski": (0, [640, 480]),
    }

    try:
        pos, default_value = poskey[name]
    except:
        return None, None
    try:
        s = args[pos]
    except:
        try:
            s = kwargs["size"]
        except:
            s = (
                kwargs.get("s", default_value)
                if name != "frei0r_src"
                else default_value
            )
    if name == "cellauto" and (
        len(args) > 0
        or any((o for o in ("filename", "f", "pattern", "p") if o in kwargs))
    ):
        s = None

    poskey, default_value = {
        "cellauto": (2, 25),  # default size condition
        "gradients": (1, 25),
        "mandelbrot": (6, 25),
        "mptestsrc": (0, 25),
        "frei0r_src": (1, None),
        "life": (1, 25),
        "sierpinski": (1, 25),
    }.get(name, (3, 25))
    try:
        r = args[pos]
    except:
        if name != "frei0r_src":
            try:
                r = kwargs["rate"]
            except:
                r = kwargs.get("r", default_value)
        else:
            r = kwargs.get("framerate", default_value)

    return r, s


def compose_source(type, expr, *args, **kwargs):

    name, *fargs = parse_filter(expr)
    if len(fargs) > 0:
        kwargs = {**kwargs, **fargs[-1]} if isinstance(fargs[-1], dict) else None
        if kwargs is not None:
            fargs = fargs[:-1]

        if len(fargs) and len(args):
            raise ValueError("Only expr or args may be non-empty.")
        elif len(fargs):
            args = fargs
    checkfcn = check_audio_source if type == "audio" else check_video_source
    return compose_filter(name, *args, kwargs), checkfcn(name, args, kwargs)


class FilterGraph:
    """FFmpeg filter graph

    FilterGraph() to instantiate empty FilterGraph object

    FilterGraph(obj) to copy-instantiate FilterGraph object from another

    FilterGraph('...') to parse an FFmpeg filter graph expression

    FilterGraph(filter_specs, input_labels, output_labels, links, sws_flags)
    to specify the compose_graph(...) arguments

    :param filter_specs: either an existing FilterGraph instance to copy, an FFmpeg
                         filter graph expression, or a nested sequence of argument
                         sequences to compose_filter() to define a filter graph.
                         For the latter option, The last element of each filter argument
                         sequence may be a dict, defining its keyword arguments,
                         defaults to None
    :type filter_specs: FilterGraph, str, or seq(seq(filter_args))
    :param input_labels: specifies labels of filter input pads which receives
                         input streams. Keys are the link labels and values
                         are sequences of (chain_id, filter_id, in_pad_id),
                         chain_id and filter_id are ints, specifying the filter
                         index in fg, and in_pad_id is an int specifying the
                         input pad, defaults to None
    :type input_labels: dict, optional
    :param output_labels: specifies labels of filter output pads which connect
                         to output streams. Keys are the link labels and values
                         are sequences of (chain_id, filter_id, out_pad_id),
                         chain_id and filter_id are ints, specifying the filter
                         index in fg, and out_pad_id is an int specifying the
                         output pad, defaults to None
    :type output_labels: dict, optional
    :param links: specifies inter-chain links. Key is a tuple of
                  (chain_id, filter_id, in_pad_id) defining the input pad
                  and value of a tuple of (chain_id, filter_id, out_pad_id)
                  defining the output pad, defaults to None
    :type links: dict, optional
    :param sws_flags: specify swscale flags for those automatically inserted
                      scalers, defaults to None
    :type sws_flags: seq of stringifyable elements with optional dict as the last
                     element for the keyword flags, optional

    Attributes:

        filter_specs (list of lists of tuples or None): list of chains of filters.
        input_labels (dict(str:(int,int,int)) or None): input pad labels. label as key,
                                                (chain, filter, pad) index as value.
        output_labels (dict(str:(int,int,int)) or None): output pad labels. label as key,
                                                 (chain, filter, pad) index as value
        links (dict((int,int,int):(int,int,int)) or None): inter-chain filter pad links.
                                                input (chain, filter, pad) index as key,
                                                output (chain, filter, pad) index as value.
        sws_flags (tuple or None): tuple defining the sws flags

    """

    def __init__(
        self,
        filter_specs=None,
        input_labels=None,
        output_labels=None,
        links=None,
        sws_flags=None,
    ):
        if filter_specs is None:
            # set all variables to empty state
            self.clear()
        elif filter_specs is not None:

            if isinstance(filter_specs, FilterGraph):
                # copy constructor
                other = filter_specs
                self.filter_specs = deepcopy(other.filter_specs)
                self.input_labels = deepcopy(other.input_labels)
                self.output_labels = deepcopy(other.output_labels)
                self.links = deepcopy(other.links)
                self.sws_flags = deepcopy(other.sws_flags)
            else:
                expr = (
                    filter_specs
                    if isinstance(filter_specs, str)
                    else compose_graph(
                        filter_specs, input_labels, output_labels, links, sws_flags
                    )
                )
                (
                    self.filter_specs,
                    self.input_labels,
                    self.output_labels,
                    self.links,
                    self.sws_flags,
                ) = parse_graph(expr)

    def __str__(self) -> str:
        return compose_graph(
            self.filter_specs,
            self.input_labels,
            self.output_labels,
            self.links,
            self.sws_flags,
        )

    def __len__(self):
        return len(self.filter_specs)

    @property
    def size(self):
        return sum((len(c) for c in self.filter_specs))

    @property
    def shape(self):
        return [len(c) for c in self.filter_specs]

    def get_chain_length(self, i):
        return len(self.filter_specs[i])

    def clear(self):
        self.filter_specs = []
        self.input_labels = {}
        self.output_labels = {}
        self.links = {}
        self.sws_flags = None

    def copy(self):
        return FilterGraph(self)

    def __getitem__(self, inds):
        get_chains, *inds = self._resolve_indices_(inds)
        if get_chains:
            return self.subgraph(
                inds[0]
                if isinstance(inds[0], int)
                else range(inds[0].start, inds[0].stop, inds[0].step)
            )
        else:
            return self.subgraph(
                inds[0],
                inds[1]
                if isinstance(inds[1], int)
                else range(inds[1].start, inds[1].stop, inds[1].step),
            )

    def __setitem__(self, inds, vals):
        do_chain, *inds = self._resolve_indices_(inds)
        if do_chain:
            if isinstance(inds[0], int):  # f[i] = v
                self.replace(inds[0], vals)
            else:
                inds = range(inds[0].start, inds[0].stop, inds[0].step)
                if inds.step > 1:  # f[i:j:k] = v (exact replacement)
                    self.replace(inds, vals)
                else:  # extension
                    self.delete_chains(inds)
                    self.insert(min(inds), vals)
        else:
            if isinstance(inds[1], int):  # f[i] = v
                self.replace(inds[0], vals, inds[1])
            else:
                inds[1] = range(inds[1].start, inds[1].stop, inds[1].step)
                if inds[1].step > 0:  # f[i:j:k] = v (exact replacement)
                    self.replace(inds[0], vals, inds[1])
                else:  # extension
                    self.delete_filters(inds[0], inds[1])
                    self.insert(min(inds[0]), vals, inds[1])

    def __delitem__(self, inds):
        del_chain, *inds = self._resolve_indices_(inds)
        if del_chain:
            self.delete_chains(
                [inds]
                if isinstance(inds[0], int)
                else range(inds[0].start, inds[0].stop, inds[0].step)
            )
        else:
            self.delete_filters(
                inds[0],
                [inds[1]]
                if isinstance(inds[1], int)
                else range(inds[1].start, inds[1].stop, inds[1].step),
            )

    def _resolve_indices_(self, inds):
        def positivify(inds, n):
            if isinstance(inds, slice):
                k = 1 if inds.step is None else inds.step
                i = (
                    (0 if k > 0 else n - 1)
                    if inds.start is None
                    else (min(inds.start, n) if k > 0 else min(n + inds.start, n - 1))
                )
                j = (
                    (n if k > 0 else -1)
                    if inds.stop is None
                    else (min(inds.stop, n) if k > 0 else min(n + inds.stop, n - 1))
                )
                inds = slice(i, j, k)
            elif inds < 0:
                inds += n
            return inds

        if isinstance(inds, tuple):
            try:
                cid, fid = inds
            except:
                raise IndexError(
                    "FilterGraph indices must be 1D (indexing chains) or 2D (indexing filters)."
                )
            if isinstance(cid, slice):
                raise IndexError(
                    "Chains cannot be slice indexed to index filter_specs."
                )
            try:
                self.filter_specs[cid][fid]
            except:
                raise IndexError("Invalid index to filters.")

            return False, cid, positivify(fid, self.get_chain_length(cid))
        else:
            try:
                self.filter_specs[inds]
            except:
                raise IndexError("Invalid index to filter chains.")

            return True, positivify(inds, len(self.filter_specs))

    def _get_chain(self, cid):
        n = len(self.filter_specs)
        if n < cid:
            return self.filter_specs[cid], False
        self.filter_specs.extend([[]] * (cid - n + 1))
        return self.filter_specs[-1], True

    def append_filter(
        self,
        filter_spec,
        chain_id=0,
        input_links=None,
        output_links=None,
        adjust_out_labels=True,
    ):
        """append a new filter

        :param filter_spec: filter description or arguments for compose_filter()
        :type filter_spec: str or arg sequence for compose_filter()
        :param chain_id: [description], defaults to 0
        :type chain_id: int, optional
        :param input_links: [description], defaults to None
        :type input_links: [type], optional
        :param output_links: [description], defaults to None
        :type output_links: [type], optional
        :param adjust_out_labels: [description], defaults to True
        :type adjust_out_labels: bool, optional
        """
        chain, new_chain = self._get_chain(chain_id)
        fpos = len(chain)
        chain.append(filter_spec)
        if not new_chain and fpos and adjust_out_labels:
            # keep all the labels from the end of the chain
            self.output_labels = {
                k: (
                    (cid, fpos, pid)
                    if cid == chain_id and fid == fpos - 1
                    else (cid, fid, pid)
                )
                for k, (cid, fid, pid) in self.output_labels.items()
            }

            self.links = {
                k: (
                    (cid, fpos, pid)
                    if cid == chain_id and fid == fpos - 1
                    else (cid, fid, pid)
                )
                for k, (cid, fid, pid) in self.links.items()
            }

        if input_links is not None:
            for pid, label in enumerate(input_links):
                id = (chain_id, fpos, pid)
                if isinstance(label, str):
                    self.input_labels[label] = id
                else:
                    self.links[id] = tuple(label)

        if output_links is not None:
            for pid, label in enumerate(output_links):
                id = (chain_id, fpos, pid)
                if isinstance(label, str):
                    self.output_labels[label] = id
                else:
                    self.links[tuple(label)] = id

    def set_link(self, input_link, output_link, overwrite=False):
        """set an internal or external link

        :param input_link: either filter input pad specifier or label of the output pad
        :type input_link: int or str
        :param output_link: either filter output pad specifier or label of the input pad
        :type output_link: int or str
        :param overwrite: True to overwrite existing link or label, defaults to False
        :type overwrite: bool, optional

        A filter pad specifier is a 3-int sequence: (chain_id, filter_id, pad_id). It specifies the target filter and its
        I/O pad to create a link. Chain_id is the index of the filter chain that the filter belongs to, and filter_id is
        the index of the filter within the chain. Both of these ids may be negative to specify wrt the end of the sequence.
        For example, chain_id=-2 picks the filter chain, second from last, and filter_id=-1 picks the last filter of the chain.
        I/O pad index is not absolute. Filter graph expression will be list I/O pad labels in the sorted order of the pad indices.

        Examples:

        ```python
            fg.set_link((0,0,0), 'in') # set the first input pad of the first filter of the first chain to be labeled "in"
            fg.set_link('out', (0,-1,0)) # set the first output pad of the last filter of the first chain to be labeled "out"
            fg.set_link((-1,0,1), (1,-1,0)) # link the second input pad of the first filter of the last chain to be linked to
                                            # the first output pad of the last filter of the second chain to be labeled "out"
        ```

        """

        def adjust_index(l, nc, nf):
            return (
                l[0] + nc if l[0] < 0 else l[0],
                l[1] + nf if l[1] < 0 else l[1],
                l[2],
            )

        def del_label(labels, l):
            dup = next((k for k, v in labels.items() if v == l), None)
            if dup:
                del labels[dup]

        def del_link(l, is_input):
            self.links = {
                k: v for k, v in self.links.items() if (k if is_input else v) != l
            }

        in_label = isinstance(input_link, str)
        out_label = isinstance(output_link, str)
        if in_label and out_label:
            raise ValueError(
                "Both input_link and output_link cannot be labels. One or both must be a filter pad specifier."
            )

        n = len(self)

        # input filter pad specified
        if not in_label:
            # make sure the sequence is a tuple
            input_link = adjust_index(
                input_link, n, self.get_chain_length(input_link[1])
            )
            # check for duplicate use of the input filter pad
            if overwrite:  # delete all existing
                del_label(self.input_labels, input_link)
                del_link(input_link, True)
            elif input_link in self.input_labels.values() or input_link in self.links:
                raise ValueError(
                    "specified input_link filter pad has already been linked."
                )

        if not out_label:
            # make sure the sequence is a tuple
            output_link = adjust_index(
                output_link, n, self.get_chain_length(output_link[1])
            )

            if overwrite:
                del_label(self.output_labels, output_link)
                del_link(output_link, False)
            elif (
                output_link in self.output_labels.values()
                or output_link in self.links.values()
            ):
                raise ValueError(
                    "specified output_link filter pad has already been linked."
                )

        if in_label:  # add to output_labels
            if overwrite:
                if input_link in self.input_labels:
                    del self.input_labels[input_link]
            else:
                if input_link in self.input_labels or input_link in self.output_labels:
                    raise ValueError(
                        f"filter pad label '{input_link}' is already in use."
                    )
            self.output_labels[input_link] = output_link
        elif out_label:  # add to input_labels
            if overwrite:
                if output_link in self.output_labels:
                    del self.output_labels[output_link]
            else:
                if (
                    output_link in self.input_labels
                    or output_link in self.output_labels
                ):
                    raise ValueError(
                        f"filter pad label '{output_link}' is already in use."
                    )
            self.input_labels[output_link] = input_link
        else:  # add to links
            self.links[input_link] = output_link

    def subgraph(self, chain_ids, filter_ids=None, copy_sws_flags=False):

        chain_is_int = isinstance(chain_ids, int)

        filter_specs = (
            self.filter_specs[chain_ids]
            if chain_is_int
            else [self.filter_specs[i] for i in chain_ids]
        )

        if filter_ids is None:
            # subgraph chains
            chain_lut = (
                {chain_ids: 0}
                if chain_is_int
                else {v: i for i, v in enumerate(chain_ids)}
            )

            def _gather_labels(labels):
                return {
                    k: (chain_lut[v[0]], *v[1:])
                    for k, v in labels.items()
                    if v[0] in chain_lut
                }

            in_labels = _gather_labels(self.input_labels)
            out_labels = _gather_labels(self.output_labels)
            links = {
                (chain_lut[k[0]], *k[1:]): (chain_lut[v[0]], *v[1:])
                for k, v in self.links.items()
                if k[0] in chain_lut and v[0] in chain_lut
            }
        else:
            # subgraph filters of a chain
            if not chain_is_int:
                raise ValueError(
                    "only filters from one filter-chain can be subgraphed together"
                )

            filt_is_int = isinstance(filter_ids, int)

            filter_specs = (
                filter_specs[filter_ids]
                if filt_is_int
                else [f for i, f in enumerate(filter_specs) if i in filter_ids]
            )

            filt_lut = (
                {filter_ids: 0}
                if filt_is_int
                else {v: i for i, v in enumerate(set(filter_ids))}
            )

            def _gather_labels(labels):
                return {
                    k: (0, filt_lut[v[1]], v[2])
                    for k, v in labels.items()
                    if v[0] == chain_ids and v[1] in filt_lut
                }

            in_labels = _gather_labels(self.input_labels)
            out_labels = _gather_labels(self.output_labels)
            links = {
                (0, filt_lut[k[1]], k[2]): (0, filt_lut[v[1]], v[2])
                for k, v in self.links.items()
                if k[0] == chain_ids
                and v[0] == chain_ids
                and k[1] in filt_lut
                and v[1] in filt_lut
            }

        return FilterGraph(
            [filter_specs] if chain_is_int else filter_specs,
            in_labels,
            out_labels,
            links,
            self.sws_flags if copy_sws_flags else None,
        )

    def _update_links(self, lut, i=None):
        """update input_labels, output_labels, and links

        :param lut: key-existing chain or filter index; value-new chain or filter index
        :type lut: dict
        :param i: chain index to update filters on the ith chain, defaults to None
        :type i: int, optional

        Any element not included in lut gets dropped
        """

        def matcher_c(v):
            return v[0] in lut

        def matcher_f(v):
            return v[0] == i and v[1] in lut

        matcher = matcher_c if i is None else matcher_f

        def updater_c(v):
            return (lut[v[0]], *v[1:])

        def updater_f(v):
            return (v[0], lut[v[1]], v[2])

        updater = updater_c if i is None else updater_f

        self.input_labels = {
            k: updater(v) for k, v in self.input_labels.items() if matcher(v)
        }
        self.output_labels = {
            k: updater(v) for k, v in self.output_labels.items() if matcher(v)
        }
        self.links = {
            updater(k): updater(v)
            for k, v in self.links.items()
            if matcher(k) and matcher(v)
        }

    def _add_links(self, src, chain_index, filter_index=None, overwrite=True):
        def appender_c(dst_labels, src_labels, update_key):
            for k, v in src_labels.items():
                if update_key:
                    k = (k[0] + chain_index, *k[1:])
                if overwrite or k not in dst_labels:
                    dst_labels[k] = v[0] + chain_index, *v[1:]

        def appender_f(dst_labels, src_labels, update_key):
            for k, v in src_labels.items():
                if update_key:
                    k = (k[0] + chain_index, k[1] + filter_index, k[2])
                if overwrite or k not in dst_labels:
                    dst_labels[k] = (v[0] + chain_index, v[1] + filter_index, v[2])

        appender = appender_c if filter_index is None else appender_f

        appender(self.input_labels, src.input_labels, False)
        appender(self.output_labels, src.output_labels, False)
        appender(self.links, src.links, True)

    def delete_chains(self, chain_ids, inplace=True):
        dst = self if inplace else FilterGraph(self)  # make copy

        # LUT of keepers and their new id's
        chain_ids = set(chain_ids)
        lut = {
            j: i
            for i, j in enumerate((i for i in range(len(dst)) if i not in chain_ids))
        }
        dst._update_links(lut)

        # delete specified filter-chains
        dst.filter_specs = [c for i, c in enumerate(dst.filter_specs) if i in lut]

        if not inplace:
            return dst

    def delete_filters(self, chain_id, filter_ids, inplace=True):
        # subgraph filters of a chain
        dst = self if inplace else FilterGraph(self)  # make copy

        # delete specified filter-chains
        chain = dst.filter_specs[chain_id]
        n = len(chain)

        filter_ids = set(filter_ids)

        # purge voided label & link
        lut = {j: i for i, j in enumerate((i for i in range(n) if i not in filter_ids))}
        dst._update_links(lut, chain_id)

        dst.filter_specs[chain_id] = [c for i, c in enumerate(chain) if i in lut]

        if not inplace:
            return dst

    def append(
        self, other, chain_id=None, links_from=None, links_to=None, inplace=True
    ):
        """append another FilterGraph to this instance

        :param other: other filter graph to be appended
        :type other: FilterGraph
        :param chain_id: specify chain index to append to only if appending
                         serially to an existing filter chain, defaults to None
        :type chain_id: int, optional
        :param inplace: If True, do operation in-place and return None, defaults to True
        :type inplace: bool, optional
        :return: FilterGraph with the appended filter chains or None if inplace=True.
        :rtype: FilterGraph or None
        """
        dst = self if inplace else FilterGraph(self)  # make copy

        if chain_id is None:
            # insert filter chains
            n = len(dst)
            dst.filter_specs.extend(other.filter_specs)
            dst._add_links(other, n)
            if links_from is not None:
                # connect input of the self from input of other
                for ldst, lsrc in links_from.items():
                    dst.set_link(
                        tuple(lsrc),
                        (ldst[0] if ldst[0] < 0 else n + ldst[0], ldst[1], ldst[2]),
                        True,
                    )

            if links_to is not None:
                # connect output of the self to input of other
                for ldst, lsrc in links_to.items():
                    dst.set_link(
                        (ldst[0] if ldst[0] < 0 else n + ldst[0], ldst[1], ldst[2]),
                        tuple(lsrc),
                        True,
                    )
        else:
            if len(other) > 1:
                raise ValueError(
                    "other FilterGraph must have only one chain to append it to a chain."
                )
            n = dst.get_chain_length(chain_id)
            dst.filter_specs[chain_id].extend(other.filter_specs[0])
            dst._add_links(other, chain_id, n)
            if links_from is not None:
                # connect input of the self from input of other
                for ldst, lsrc in links_from.items():
                    dst.set_link(
                        tuple(lsrc),
                        (ldst[0], ldst[1] if ldst[1] < 0 else n + ldst[1], ldst[2]),
                        True,
                    )

            if links_to is not None:
                # connect output of the self to input of other
                for ldst, lsrc in links_to.items():
                    dst.set_link(
                        (ldst[0], ldst[1] if ldst[1] < 0 else n + ldst[1], ldst[2]),
                        tuple(lsrc),
                        True,
                    )

        if not inplace:
            return dst

    def extend(self, *args, copy_sws_flags=False, **kwargs):
        other = (
            args[0]
            if len(args) == 1 and isinstance(args[1], FilterGraph) and not len(kwargs)
            else FilterGraph(*args, **kwargs)
        )
        n = len(self.filter_specs)  # offset on chain id
        self.filter_specs.extend(other.filter_specs)
        self._add_links(other, n)
        if copy_sws_flags and other.sws_flags is not None:
            self.sws_flags = deepcopy(other.sws_flags)

    # def __imul__(self, other):
    #     self.filter_specs *= other

    def insert(self, chain_index, fg, filter_index=None, copy_sws_flags=False):
        n = len(fg)

        if filter_index is None:
            # insert filter chains
            self.filter_specs.insert(chain_index, fg.filter_specs)
            lut = {i: i if i < chain_index else i + n for i in range(len(self))}
            self._update_links(lut)
            self._add_links(fg, chain_index)
        else:
            if n > 1:
                raise ValueError("fg must be a chain if filter_index is specified")
            n = fg.get_chain_length(0)
            self.filter_specs[chain_index].insert(filter_index, fg.filter_specs)
            lut = {
                i: i if i < filter_index else i + n
                for i in range(self.get_chain_length(chain_index))
            }
            self._update_links(lut, chain_index)
            self._add_links(fg, chain_index, filter_index)

        if copy_sws_flags and fg.sws_flags is not None:
            self.sws_flags = deepcopy(fg.sws_flags)

    def replace(
        self, chain_index, fg, filter_index=None, inplace=True, keep_links=True
    ):

        dst = self if inplace else FilterGraph(self)  # make copy

        if filter_index is None:  # replace chains
            n = len(fg)
            if isinstance(chain_index, int):
                chain_index = [chain_index]
            if n != 1 and n != len(chain_index):
                raise ValueError("the lengths of chain_index and fg must match")

            fg_src = fg if n == 1 else None

            if not keep_links:
                lut = {i: i for i in range(len(dst)) if i not in chain_index}
                dst._update_links(lut)

            for i in chain_index:
                if n > 1:
                    fg_src = fg[i]
                    if len(fg_src) != 1:
                        raise ValueError(
                            "Each element of fg must be a single-chain filtergraph."
                        )
                dst.filter_specs[i] = fg_src.filter_specs[0]
                dst._add_links(fg_src, i, overwrite=not keep_links)

            # if keep_links:
            # only keep valid links

        else:  # replace filters on the (chain_index)th chain
            if not isinstance(chain_index, int):
                raise ValueError("chain_index must be an int to replace filters.")
            if isinstance(filter_index, int):
                filter_index = [filter_index]

            if len(fg) > 1:
                raise ValueError("fg must be a single-chain filter graph.")
            n = fg.get_chain_length(0)
            if n != 1 and n != len(filter_index):
                raise ValueError(
                    "the lengths of fg[0] must be one or equals the length of filter_index"
                )

            # drop the links of the existing chain to be replaced
            lut = {
                i: i
                for i in range(dst.get_chain_length(chain_index))
                if i not in filter_index
            }
            dst._update_links(lut, chain_index)

            for i, j in enumerate(filter_index):
                dst.filter_specs[chain_index][j] = (
                    fg.filter_specs[0][i] if n > 1 else fg.filter_specs[0][0]
                )
                dst._add_links(fg, chain_index, i, overwrite=not keep_links)

        if not inplace:
            return dst


def compose(expr, **kwargs):
    """compose filter, filter chain, or filter graph

    :return: filter graph expression
    :rtype: str

    Auto-detects which filter/chain/graph based on the arguments.

    See compose_filter(), compose_chain(), & compose_graph() for the
    argument options.

    Keyword arguemts maybe provided as the last sequential argument.

    """

    if expr is None or isinstance(expr, (str, FilterGraph)):
        return expr

    return compose_graph(*expr, **kwargs)


def video_basic_filter(
    fill_color=None,
    remove_alpha=None,
    scale=None,
    crop=None,
    flip=None,
    transpose=None,
    square_pixels=None,
):
    vfilters = []

    bg_color = fill_color or "white"

    if remove_alpha:
        vfilters.append(f"color=c={bg_color}[l1];[l1][in]scale2ref[l2],[l2]overlay")

    if square_pixels == "upscale":
        vfilters.append("scale='max(iw,ih*dar):max(iw/dar,ih):eval=init',setsar=1/1")
    elif square_pixels == "downscale":
        vfilters.append("scale='min(iw,ih*dar):min(iw/dar,ih):eval=init',setsar=1/1")
    elif square_pixels == "upscale_even":
        vfilters.append("scale='trunc(max(iw,ih*dar)/2)*2:trunc(max(iw/dar,ih)/2)*2:eval=init',setsar=1/1")
    elif square_pixels == "downscale_even":
        vfilters.append("scale='trunc(min(iw,ih*dar)/2)*2:trunc(min(iw/dar,ih)/2)*2:eval=init',setsar=1/1")
    elif square_pixels is not None:
        raise ValueError(f"unknown `square_pixels` option value given: {square_pixels}")

    if crop:
        try:
            assert not isinstance(crop, str)
            vfilters.append(compose_filter("crop", *crop))
        except:
            vfilters.append(compose_filter("crop", crop))

    if flip:
        try:
            ftype = ("", "horizontal", "vertical", "both").index(flip)
        except:
            raise Exception("Invalid flip filter specified.")
        if ftype % 2:
            vfilters.append("hflip")
        if ftype >= 2:
            vfilters.append("vflip")

    if transpose is not None:
        try:
            assert not isinstance(transpose, str)
            vfilters.append(compose_filter("transpose", *transpose))
        except:
            vfilters.append(compose_filter("transpose", transpose))

    if scale:
        try:
            scale = [int(s) for s in scale.split("x")]
        except:
            pass
        try:
            assert not isinstance(scale, str)
            vfilters.append(compose_filter("scale", *scale))
        except:
            vfilters.append(compose_filter("scale", scale))

    return ",".join(vfilters)
