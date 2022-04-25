import re, itertools
from collections.abc import Sequence
from copy import deepcopy

from .. import utils, caps


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

        # escape special characters
        s = re.sub(r"([':\\])", r"\\\1", value)

        # use quote if value start or ends with space
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
                         input streams. Keys are sequences of (chain_id, 
                         filter_id, in_pad_id), and values are the link labels
                         (either the pad label or input stream spec) 
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

    def find_input_pad(self, label=None):
        try:
            return self.input_labels[label or "in"]
        except:
            if label:
                raise ValueError(f'input label "{label}" is not defined.')
            if not len(self.filter_specs):
                raise ValueError("No filter defined in the graph.")
            pad = (0, 0, 0)
            if pad in self.links or pad in self.input_labels.values():
                raise ValueError(
                    "cannot use the first input pad of the first filter: already in use."
                )
            return pad

    def find_output_pad(self, label=None):
        try:
            return self.output_labels[label or "out"]
        except:
            if label:
                raise ValueError(f'output label "{label}" is not defined.')
            i = len(self.filter_specs) - 1
            try:
                j = len(self.filter_specs[-1]) - 1
            except:
                raise ValueError("No filter defined in the graph.")

            pad = (i, j, 0)
            if pad in self.links.values() or pad in self.output_labels.values():
                raise ValueError(
                    "cannot find output label and the first output pad of the last filter already in use."
                )
            return pad


def FilterChain(
    filter_specs, input_labels=None, output_labels=None, autolabel=False, sws_flags=None
):
    """convenience function to create a single-chain FilterGraph instance

    :param filter_specs: specifications of the filters to compose a filterchain
    :type filter_specs: Sequence[filter_spec]
    :param input_labels: specifies labels of filter input pads which receive
                         input streams. If str, it defines the label of the first
                         input pad. If dict, keys are the link labels and values
                         specify which input pad. If a dict value is int, it's the
                         input pad index of the first filter. If the value is tuple
                         of 2 ints, they are indices of (filter, pad) defaults to None
    :type input_labels: str, dict[str,int or tuple[int,int]], optional
    :param output_labels: specifies labels of filter output pads which send
                          output streams. If str, it defines the label of the first
                          output pad. If dict, keys are the link labels and values
                          specify which output pad. If a dict value is int, it's the
                          output pad index of the last filter. If the value is tuple
                          of 2 ints, they are indices of (filter, pad) defaults to None
    :type output_labels: str, dict[str,int], optional
    :param autolabel: True to add "in" input label if input_labels is not specified
                     and to add "out" output label if output_labels is not specified.
    :type autolabel: bool, optional
    :param sws_flags: specify swscale flags for those automatically inserted
                      scalers, defaults to None
    :type sws_flags: seq of stringifyable elements with optional dict as the last
                     element for the keyword flags, optional
    :return: single-chain FFmpeg filtergraph
    :rtype: FilterGraph
    """

    def set_label(labels, default_label, arg_name):
        if isinstance(labels, str):
            labels = {labels: (0, 0, 0)}
        elif isinstance(labels, dict):
            labels = {k: (0, 0, v) if isinstance(v) else (0, *v) for k, v in labels}
        elif labels is not None:
            raise ValueError(f"invalid {arg_name} argument.")
        elif autolabel:
            labels = {default_label: (0, 0, 0)}
        return labels

    input_labels = set_label(input_labels, "in", "input_labels")
    output_labels = set_label(output_labels, "out", "output_labels")

    return FilterGraph([filter_specs], input_labels, output_labels, sws_flags)


def Filter(
    filter_spec, input_labels=None, output_labels=None, autolabel=False, sws_flags=None
):
    """convenience function to create a single-filter FilterGraph instance

    :param filter_specs: specifications of the filters to compose a filterchain
    :type filter_specs: Sequence[filter_spec]
    :param input_labels: specifies labels of filter input pads which receive
                         input streams. If str, it defines the label of the first
                         input pad. If dict, keys are the link labels and values
                         specify which input pad, defaults to None
    :type input_labels: str, dict[str,int], optional
    :param output_labels: specifies labels of filter output pads which send
                          output streams. If str, it defines the label of the first
                          output pad. If dict, keys are the link labels and values
                          specify which output pad, defaults to None
    :type output_labels: str, dict[str,int], optional
    :param autolabel: True to add "in" input label if input_labels is not specified
                     and to add "out" output label if output_labels is not specified.
    :type autolabel: bool, optional
    :param sws_flags: specify swscale flags for those automatically inserted
                      scalers, defaults to None
    :type sws_flags: seq of stringifyable elements with optional dict as the last
                     element for the keyword flags, optional
    :return: single-filter FFmpeg filtergraph
    :rtype: FilterGraph
    """

    def set_label(labels, default_label, arg_name):
        if isinstance(labels, str):
            labels = {labels: (0, 0, 0)}
        elif isinstance(labels, dict):
            labels = {k: (0, 0, v) for k, v in labels}
        elif labels is not None:
            raise ValueError(f"invalid {arg_name} argument.")
        elif autolabel:
            labels = {default_label: (0, 0, 0)}
        return labels

    input_labels = set_label(input_labels, "in", "input_labels")
    output_labels = set_label(output_labels, "out", "output_labels")

    return FilterGraph([[filter_spec]], input_labels, output_labels, sws_flags)


def join(*fgs, joiner=None, n_in=None, unconnected=False):
    """join filtergraphs

    Three types of connections are possible:

    * Series connection: 2 filtergraphs connected in series
    * Series connection with a joining filter: number of filtergraphs dictated by
      the joining filter.
    * No connection: filtergraphs are independently operating

    :param \\*fgs: filtergraphs to be joined. If graphs are connected (connect=True)
                   the input or output pad of each filtergraph may be specified by
                   passing in a pair of filtergraph and its connecting pad.

                   Its connecting pad, specified either
                   by its label or pad id tuple (chain, filter, pad). If pad not
                   given, the first output pad of the last filter of the last filterchain
                   is connected of the input filtergraph, and the first output pad
                   of the first filter of the first filterchain is selected for output
                   filtergraph
    :type \\*fgs: tuple[FilterGraph or (FilterGraph, str or tuple[int] or str]
    :param joiner: joining filter, e.g., overlay, defaults to None
    :type joiner: str or filter_spec tuple, optional
    :param n_in: number of input filtergraphs to the joining filter, defaults to None
    :type n_in: int, optional
    :param unconnected: True to make no connections between fgs, defaults to False
    :type unconnected: bool, optional

    Examples
    --------

    fg3 = join(fg1,fg2)
    fg4 = join(fg1,fg2,'out','overlay')

    """

    # check input fgs
    if unconnected:
        # parallel fgs, no joining
        joiner = n_in = None
    else:
        if joiner is None:  # series join
            if n_in != 1 or len(fgs) != 2:
                raise ValueError(
                    "Only 2 filtergraphs can be joined in series at a time."
                )
            n_in = 1
        else:  # joined with a joiner filter
            try:
                name = joiner if isinstance(joiner, str) else joiner[0]
                info = caps.filters()[name]
                n_in = info["num_inputs"] if isinstance(info["num_inputs"], int) else 2
            except:
                raise ValueError("invalid joiner argument: filter name is invalid")

    # split fg and pad
    pads = []

    def analyze_input(i, fg):
        if unconnected:
            if isinstance(fg, FilterGraph):
                return fg
            raise ValueError(
                f"fgs must be all FilterGraph objects for unconnected join"
            )
        if isinstance(fg, str):
            # in/out label
            pad = fg
            fg = None
        elif isinstance(fg, FilterGraph):
            pad = fg.find_output_pad() if i < n_in else fg.find_input_pad()
        else:
            try:
                fg, pad = fg
            except:
                raise ValueError(f"invalid filtergraph/label specification: {fg}")
            if isinstance(pad, str):
                pad = fg.find_output_pad(pad) if i < n_in else fg.find_input_pad(pad)
        pads.append(pad)
        return fg and fg.copy()

    fgs = [analyze_input(i, fg) for i, fg in enumerate(fgs)]

    fgiter = (i_fg for i_fg in enumerate(fgs) if i_fg[1])
    i0, fg0 = next(fgiter)
    i0 = len(fg0)  # chain id offset
    for i, fg in fgiter:
        fg0.filter_specs += fg.filter_specs
        

    n = [len(fg) if fg else 0 for fg in fgs]  # number of chains

    pass


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
        vfilters.append(
            "scale='trunc(max(iw,ih*dar)/2)*2:trunc(max(iw/dar,ih)/2)*2:eval=init',setsar=1/1"
        )
    elif square_pixels == "downscale_even":
        vfilters.append(
            "scale='trunc(min(iw,ih*dar)/2)*2:trunc(min(iw/dar,ih)/2)*2:eval=init',setsar=1/1"
        )
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
