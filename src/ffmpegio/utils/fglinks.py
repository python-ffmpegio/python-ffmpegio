import re
from collections import UserDict, abc
from . import is_stream_spec
from ..errors import FFmpegioError


class GraphLinks(UserDict):
    class Error(FFmpegioError):
        pass

    @staticmethod
    def iter_dst_ids(dsts, include_labels=False):
        """helper generator to work dsts ids

        :param dsts: dsts pad id or ids
        :type dsts: tuple(int,int,int) | seq(tuple(int,int,int)) | None
        :param include_labels: True to yield None for each unconnected labels, defaults to False to skip None dsts
        :param include_labels: bool, optional
        :yield: individual dst id, immediately exits if None
        :rtype: tuple(int,int,int)|None
        """

        if dsts is None:
            if include_labels:
                yield dsts
        elif isinstance(dsts[0], int):
            yield dsts
        else:
            for dst in dsts:
                if not (dsts is None and include_labels):
                    yield dst

    @staticmethod
    def validate_label(label, named_only=False, no_stream_spec=False):
        try:
            assert re.match(r"[a-zA-Z0-9_]+$", label) or (
                not no_stream_spec and is_stream_spec(label, None)
            )
        except:
            if named_only or not isinstance(label, int):
                msg = f'{label} is not a valid link label. A link label must be a string with only alphanumeric and "_" characters'
                raise GraphLinks.Error(
                    msg + "."
                    if named_only
                    else msg + " or an int for unnamed internal link."
                )

    @staticmethod
    def validate_pad_id(id):

        if id is None:
            return

        if not (
            isinstance(id, (tuple))
            and len(id) == 3
            and all((isinstance(i, int) and i >= 0 for i in id))
        ):
            raise GraphLinks.Error(
                f"{id} is not a valid filter pad ID. Filter pad ID must be a 3-element tuple: (chain id, filter id, pad id)"
            )

    @staticmethod
    def validate_pad_id_pair(ids):

        try:
            assert len(ids) == 2
        except:
            raise GraphLinks.Error(
                f"Link value must be a 2-element tuple with dst and src pad ids"
            )

        (dst, src) = ids
        GraphLinks.validate_pad_id(src)

        i = -1
        for i, d in enumerate(GraphLinks.iter_dst_ids(dst, True)):
            if d is None and src is None:
                raise GraphLinks.Error(
                    f"multi-id input label item cannot be None."
                )
            GraphLinks.validate_pad_id(d)
        nel = i + 1

        if src is None and nel == 0:
            raise GraphLinks.Error(f"both src and dst cannot be None.")

        if dst is not None and not isinstance(dst[0], int) and nel < 2:
            raise GraphLinks.Error(
                f"multi-id dst link item must define more than 1 element."
            )

    @staticmethod
    def validate_item(label, pads):
        GraphLinks.validate_pad_id_pair(pads)  # this fails if None-None pair

        GraphLinks.validate_label(label, no_stream_spec=pads[1] is not None)

        # stream specifier can only be used as input label
        if is_stream_spec(label, True) and pads[1] is not None:
            raise GraphLinks.Error(
                f"Input stream specifier ({label}) can only be used as an input label."
            )

        # unnamed link cannot be a pad label
        if isinstance(label, int) and (
            not len(list(GraphLinks.iter_dst_ids(pads[0]))) or pads[1] is None
        ):
            raise GraphLinks.Error(
                f"Unnamed (integer) links must specify both dst and src."
            )

    @staticmethod
    def validate(data):

        dsts = set()  # dst cannot be repeated

        # validate each link
        for label, pads in data.items():
            GraphLinks.validate_item(label, pads)
            for d in GraphLinks.iter_dst_ids(pads[0]):
                # dst pad id must be unique
                if d in dsts:
                    raise GraphLinks.Error(
                        f"Duplicate entries of dst pad id {d} found (must be unique)"
                    )
                if d is not None:
                    dsts.add(d)

    @staticmethod
    def format_value(dsts, src, modifier=None):

        if modifier:
            if src is not None:
                src = modifier(src)
            modified = tuple(
                (
                    d if d is None else modifier(d)
                    for d in GraphLinks.iter_dst_ids(dsts, True)
                )
            )
            n = len(modified)
            dsts = None if n < 1 else modified[0] if n < 2 else modified
        elif dsts is not None and isinstance(dsts[0], tuple):
            # make sure dsts sequence of ids is a tuple
            dsts = tuple(dsts)

        return (dsts, src)

    # regex pattern to identify a label with a trailing number
    LabelPattern = re.compile(r"(.+?)(\d+)?$")

    def __init__(self, links=None):
        # validate input arg
        if links is not None and not isinstance(links, GraphLinks):
            try:
                self.validate(links)
            except GraphLinks.Error as e:
                raise e
            except:
                raise TypeError(
                    "links argument must be a properly formatted dict type."
                )

            links = {k: self.format_value(*v) for k, v in links.items()}

        # label auto-renaming database
        self.label_lookup = {int: -1}

        # calls update() if links set
        super().__init__(links or {})

    def _register_label(self, label):
        """check the label name for duplicate, adjust as needed

        :param label: suggested new label name
        :type label: str|int
        :return: safe new label name
        :rtype: str
        """

        lut = self.label_lookup

        if isinstance(label, (type(None), int)):
            label = lut[int] = lut[int] + 1
            return label

        if is_stream_spec(label, True):
            return label

        # guaranteed to match
        name, nnew = self.LabelPattern.match(label).groups()

        if name == "L":
            name = "L_"  # L is reserved for unnamed links

        if name in lut:  # matching label found
            n = lut[name]
            if nnew is None:  # new label is not numbered
                if n < 0:  # existing label not numbered
                    # number both existing and new
                    try:
                        v = self.data.pop(name)
                        self.data[f"{name}1"] = v
                        n = 2
                    except:
                        # the existing label has been deleted
                        return label
                else:  # existing label numbered
                    n += 1
            else:  # new label is numbered
                if n < 0:  # existing unnumbered, must modify it, too
                    # number both existing and new
                    n = 0 if nnew == "0" else 1
                    try:
                        v = self.data.pop(name)
                        self.data[f"{name}{n}"] = v
                    except:
                        # the existing label has been deleted
                        n -= 1
                n += 1
            label = f"{name}{n}"
        else:  # matching label not found, keep the label as is but log it
            if nnew is None:  # new label not numbered
                n = -1
            else:  # new label numbered
                n = 0 if nnew == "0" else 1
                label = f"{name}{n}"
        lut[name] = n
        return label

    def __getitem__(self, key):
        """get link item by label or by dst pad id tuple

        :param key: label name or dst pad id tuple (int,int,int)
        :type key: str or tuple(int,int,int)
        :return: link dsts-src pair
        :rtype: tuple(tuple(tuple(int,int,int))|None,tuple(int,int,int)|None)
        """
        try:
            # try as label first
            return super().__getitem__(key)
        except Exception as e:
            # try as dst id
            label = self.find_dst_label(key)
            if label is None:
                raise e
            return (label, self.data[label][1])

    def __setitem__(self, key, value):
        # can only set named key
        self.link(value[1], value[0], label=key, force=False, validate=True)

    def is_linked(self, label):
        """True if label specifies a link

        :param label: link label
        :type label: str
        :return: True if label is a link
        :rtype: bool

        If multi-dst label, True if any dst is not None
        """
        lnk = self.data.get(label, (None, None))
        return lnk[1] is not None and any(self.iter_dst_ids(lnk[0]))

    def is_input(self, label):
        """True if label specifies an input

        :param label: link label
        :type label: str
        :return: True if label is an input
        :rtype: bool
        """
        lnk = self.data.get(label, None)
        return lnk and lnk[1] is None

    def is_output(self, label):
        """True if label specifies an output

        :param label: link label
        :type label: str
        :return: True if label is an output
        :rtype: bool

        If multi-dst label, True if any dst is None
        """
        lnk = self.data.get(label, None)
        return lnk and any((d is None for d in self.iter_dst_ids(lnk[0], True)))

    def num_outputs(self, label):
        """Get number of outputs

        :param label: link label
        :type label: str
        :return: number of output (logical) pads
        :rtype: int

        If multi-dst label, True if any dst is None
        """
        lnk = self.data.get(label, None)
        return int(lnk is not None) and sum(
            (d is None for d in self.iter_dst_ids(lnk[0], True))
        )

    def iter_dsts(self, label=None):
        """Iterate over all link elements, possibly separating dst ids with
           the same label

        :param label: to iterate only on this label, defaults to None (all frames)
        :type label: str, optional
        :yield: a full link definition (dst or src may be None if input or output label, repectively)
        :rtype: tuple of label, dst id, and src id
        """

        def iter(label, dst, src):
            for d in self.iter_dst_ids(dst, True):
                yield (label, d, src)

        if label is None:
            for label, (dst, src) in self.data.items():
                for v in iter(label, dst, src):
                    yield v
        else:
            for v in iter(label, *self.data[label]):
                yield v

    def iter_links(self, label=None):
        """Iterate over only actual links, possibly separating dst ids with
           the same label

        :param label: to iterate only on this label, defaults to None (all frames)
        :type label: str, optional
        :yield: a full link definition
        :rtype: tuple of label, dst id, and src id
        """

        def iter(label, dst, src):
            if src is not None:
                for d in self.iter_dst_ids(dst):
                    yield (label, d, src)

        if label is None:
            for label, (dst, src) in self.data.items():
                for v in iter(label, dst, src):
                    yield v
        else:
            for v in iter(label, *self.data[label]):
                yield v

    def iter_inputs(self, ignore_connected=False):
        """Iterate over only input labels, possibly repeating the same label if shared among
           multiple input pad ids

        :param ignore_connected: True to exclude inputs, which are already connected to input streams, defaults to False
        :type ignore_connected: bool, optional
        :yield: a full input definition
        :rtype: tuple of label and dst id
        """
        for label, (dst, src) in self.data.items():
            if src is None and not (
                ignore_connected and isinstance(label, str) and is_stream_spec(label)
            ):
                for d in self.iter_dst_ids(dst):
                    yield (label, d)

    def iter_outputs(self, label=None):
        """Iterate over only output labels

        :param label: to iterate only on this label, defaults to None (all frames)
        :type label: str, optional
        :yield: a full output definition (same label may be used multiple times)
        :rtype: tuple of label and src id
        """

        def iter(label, dst, src):
            for d in self.iter_dst_ids(dst, True):
                if d is None:
                    yield (label, src)

        if label is None:
            # iterate over all labels
            for label, (dst, src) in self.data.items():
                for v in iter(label, dst, src):
                    yield v
        else:
            # only for the given label
            for v in iter(label, *self.data[label]):
                yield v

    def find_dst_label(self, dst):
        """get label of an input pad id

        :param dst: input filter pad id
        :type dst: tuple(int,int,int)
        :return: found label or None if no match found
        :rtype: str or None
        """
        if dst is None:
            return None
        return next((label for label, dst1, _ in self.iter_dsts() if dst == dst1), None)

    def find_src_labels(self, src):
        """get labels of a source/output pad id

        :param dst: output filter pad id
        :type dst: tuple(int,int,int)
        :return: found label or None if src is None
        :rtype: list of str or None
        """
        if src is None:
            return None
        return [label for label, (_, src1) in self.data.items() if src == src1]

    def find_input_label(self, dst):
        """get labels of an unconnected input pad id

        :param dst: input filter pad id
        :type dst: tuple(int,int,int)
        :return: found label or None if no match found
        :rtype: str or None
        """
        if dst is None:
            return None
        return next((label for label, dst1 in self.iter_inputs() if dst == dst1), None)

    def find_output_labels(self, src):
        """get labels of an unconnected source/output pad id

        :param dst: output filter pad id
        :type dst: tuple(int,int,int)
        :return: found label or None if src is None
        :rtype: list of str or None
        """
        if src is None:
            return None
        return [label for label, src1 in self.iter_outputs() if src == src1]

    def find_link_label(self, dst, src):
        if src is None or dst is None:
            return None
        return next((l for l, d, s in self.iter_links() if src == s and dst == d), None)

    def are_linked(self, dst, src):
        if src is None or dst is None:
            return False
        return any((src == s and dst == d for _, d, s in self.iter_links()))

    def unlink(self, label=None, dst=None, src=None):
        """unlink specified links

        :param label: specify all the links with this label, defaults to None
        :type label: str|int, optional
        :param dst: specify the link with this dst pad, defaults to None
        :type dst: tuple(int,int,int), optional
        :param src: specify all the links with this src pad, defaults to None
        :type src: tuple(int,int,int), optional
        """
        if label is not None:
            del self.data[label]
        if src is not None:
            for label in self.find_src_labels(src):
                del self.data[label]
        if dst is not None:
            label = self.find_dst_label(dst)
            dsts, src = self.data[label]
            if isinstance(dsts[0], int):  # unique label
                del self.data[label]
            else:  # multi-dsts label
                # depends on how many left
                dsts = tuple((d for d in dsts if d != dst))
                self.data[label] = (dsts, src) if len(dsts) > 1 else (dsts[0], src)

    def link(self, dst, src, label=None, preserve_src_label=False, force=False):
        """set a filtergraph link

        :param dst: input pad ids
        :type dst: tuple(int,int,int)
        :param src: output pad id
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

        notes:
        - Unless `force=True`, dst pad must not be already connected
        - User-supplied label name is a suggested name, and the function could
          modify the name to maintain integrity.
        - If dst or src were previously named, their names will be dropped
          unless one matches the user-supplied label.
        - No guarantee on consistency of the link label (both named and unnamed)
          during the life of the object

        """

        if src is None or dst is None:
            raise GraphLinks.Error(f"both src and dst ids must not be Nones.")

        # check if dst already exists and resolve conflict if there is one
        dst_label = self.find_dst_label(dst)
        if dst_label is not None:
            if not (force or self.is_input(dst_label)):
                raise GraphLinks.Error(f"input pad {dst} already linked.")
            if force or isinstance(self.data[dst_label][0][0], tuple):
                # if dst_label has multi-dsts, cannot reuse it
                self.unlink(dst=dst)
                dst_label = None

        # check if output label already exists. pick the first match
        src_label = (
            None
            if preserve_src_label
            else next(
                (k for k, (d, s) in self.data.items() if d is None and s == src), None
            )
        )

        # finalize the label name
        # if not defined by user, select new label to be dst or src label if found
        label = (
            label
            or (isinstance(dst_label, str) and dst_label)
            or (isinstance(src_label, str) and src_label)
            or None
        )

        if not (dst_label or src_label):
            # new label, register
            label = self._register_label(label)

        # if input label was found to be updated, remove it
        if dst_label is not None and label != dst_label:
            # remove output label
            self.unlink(label=dst_label)

        # if output label was found to be updated, remove it
        if src_label is not None and label != src_label:
            # remove output label
            self.unlink(label=src_label)

        # create the new link
        self.data[label] = (dst, src)

        return label

    def create_label(self, label, dst=None, src=None, force=None):
        """label a filter pad

        :param label: name of the new label or input stream specifier (for input label only)
        :type label: str
        :param dst: input filter pad id (or a sequence of ids), defaults to None
        :type dst: tuple(int,int,int) or seq(tuple(int,int,int)), optional
        :param src: output filter pad id, defaults to None
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

        if (src is None) == (dst is None):
            raise ValueError("src or dst (but not both) must be given.")

        # check if dst already exists and resolve conflict if there is one
        if dst:
            dsts = [dst] if isinstance(dst, tuple) else dst

            # get labels of src and dst if already exists
            dst_labels = set(
                (d for d in (self.find_dst_label(d) for d in dsts) if d is not None)
            )

            # already labeled as specified
            if len(dst_labels) == 1 and label in dst_labels:
                return label

            # if an unmatched labal is already assigned to dst
            if len(dst_labels):
                if force:
                    # drop existing if forced
                    for d in dsts:
                        self.unlink(dst=d)
                else:
                    # or throw an error
                    raise GraphLinks.Error(
                        f"the input pad(s) {dst} already linked."
                    )

            if not isinstance(dst, tuple):
                dst = tuple(dst)

        else:
            if is_stream_spec(label):
                raise GraphLinks.Error(
                    f"the output label [{label}] cannot be a stream specifier."
                )

            if label in self.find_src_labels(src):
                # already labeled as specified
                return label

        # create the link
        label = self._register_label(label)
        self.data[label] = (dst, src)
        return label

    def remove_label(self, label, dst=None):
        """remove an input/output label

        :param label: unconnected link label
        :type label: str
        :param dst: (multi-input label only) specify the input filter pad id
        :type dst: int, optional

        Removing an input label by default removes all associated filter pad ids
        unless `dst` is specified.

        """
        try:
            dsts, src = self.data[label]
        except:
            raise GraphLinks.Error(f"{label} is not a valid link label.")

        if dsts is None or (src is None and dst is None):
            # simple in/out label
            del self.data[label]
        else:
            # possible for an output label coexisting with link labels
            dsts = tuple(self.iter_dst_ids(dsts, True))
            new_dsts = tuple(
                (d for d in dsts if d is not None)
                if dst is None
                else (d for d in dsts if d is not None and d != dst)
            )
            n = len(new_dsts)
            if n == len(dsts):
                raise GraphLinks.Error(
                    f"no specified input labels found: {label} (dst={dst})."
                )

            if n < 1:
                del self.data[label]
            else:
                self.data[label] = (new_dsts[0], src) if n < 2 else (new_dsts, src)

    def rename(self, old_label, new_label):
        """rename a label

        :param old_label: existing label (named or unnamed)
        :type old_label: str or int
        :param new_label: new label name (possibly appended with a number if the label already exists)
        :type new_label: str|None
        :return: actual label name
        :rtype: str
        """
        v = self.data[old_label]
        label = self._register_label(new_label)
        del self.data[old_label]
        self.data[label] = v
        return label

    def update(
        self,
        other,
        offset=0,
        auto_link=False,
        force=False,
    ):
        """Update the links with the label/id-pair pairs from other, overwriting existing keys. Return None.

        :param other: other object to copy existing items from
        :type other: GraphLinks or a dict-like object with valid items
        :param offset: channel id offset of the copied items, defaults to 0
        :type offset: int, optional
        :param auto_link: True to connect matching input-output labels, defaults to False
        :type auto_link: bool, optional
        :param force: True to overwrite existing link dst id, defaults to False
        :type force: bool, optional
        :returns: dict of given key to the actual labels assigned
        :rtype: dict
        """
        if not isinstance(other, GraphLinks):
            try:
                assert isinstance(other, abc.Mapping)
            except Exception as e:
                raise GraphLinks.Error(
                    f"Other must be a dict-like mapping object"
                )
            self.validate(other)

        n = len(other)
        if not n:
            return {}

        # set chain index adjustment function if offset given
        adj_fn = (lambda id: (id[0] + offset, *id[1:])) if offset else None

        # prep other's dsts value (adjust chain id & check for duplicate)
        to_unlink = []  # for forcing dst

        def chk_dst(d, do):
            if any((d == d0 for _, d0, _ in self.iter_dsts())):
                if force:
                    to_unlink.append(d)
                else:
                    raise GraphLinks.Error(
                        f"dst id {do} with chain id offset {offset or 0} conflicts with existing dst "
                    )

        def prep_ids(dsts, src):
            dsts_adj, src = (
                self.format_value(dsts, src, adj_fn) if offset else (dsts, src)
            )
            if dsts is not None:
                if isinstance(dsts[0], int):
                    chk_dst(dsts_adj, dsts)
                else:
                    for d, d0 in zip(dsts_adj, dsts):
                        chk_dst(d, d0)
            return dsts_adj, src

        other = [(k, prep_ids(*v)) for k, v in other.items()]

        # delete dsts to be overwritten
        for dst in to_unlink:
            self.unlink(dst=dst)

        # process each input item
        def process_item(label, dsts, src):
            new_label = True
            if label in self.data:
                dsts_self, src_self = self.data[label]
                if auto_link:
                    # try to link matching input & output pads
                    if dsts is None and src_self is None:
                        self.data[label] = (dsts_self, src)
                        return label
                    elif src is None and dsts_self is None:
                        self.data[label] = (dsts, src_self)
                        return label

                if src == src_self:
                    # if links from the same source, merge
                    dsts = tuple(
                        (
                            *self.iter_dst_ids(dsts_self, True),
                            *self.iter_dst_ids(dsts, True),
                        )
                    )
                    new_label = False

            if new_label:
                label = self._register_label(label)
            self.data[label] = (dsts, src)
            return label

        return {label: process_item(label, dsts, src) for label, (dsts, src) in other}

    def get_repeated_src_info(self):
        """return a nested dict with an item per multi-destination filter output pad id's.

        :return: dict of multi-destination srcs
        :rtype: dict

        { filter output pad id: {
            output link label : None
            filter input pad id: link label
        }}
        """
        # iterate all the sources with multiple destinations
        # dict(key=src id: value=dict(key=dst id|None: value=label|# of output labels))

        # gather all sources, rename labels to guarantee uniqueness
        srcs = {}
        for label, (dsts, src) in self.data.items():
            if src is None:
                continue
            if src in srcs:
                item = srcs[src]
            else:
                item = srcs[src] = {}

            dsts = tuple(self.iter_dst_ids(dsts, True))
            if len(dsts) > 1:
                item.update({f"{label}_{i}": dst for i, dst in enumerate(dsts)})
            else:
                item[label] = dsts[0]

        # drop all sources with single-destination
        return {src: dsts for src, dsts in srcs.items() if len(dsts) > 1}

    def _modify_pad_ids(self, select, adjust):
        """generic pad id modifier

        :param select: function to select a pad id to modify
        :type select: Callable: select(id)->bool
        :param adjust: function to adjust the selected pad id
        :type adjust: Callable: adjust(id)->new_id

        """

        def adjust_pair(dsts, src):
            if src is not None and select(src):
                src = adjust(src)
            if dsts is not None:
                if isinstance(dsts[0], int):
                    if select(dsts):
                        dsts = adjust(dsts)
                else:
                    dsts = tuple(adjust(d) if select(d) else d for d in dsts)
            return (dsts, src)

        self.data = {label: adjust_pair(*value) for label, value in self.data.items()}

    def adjust_chains(self, pos, len):
        """insert/delete contiguous chains from fg

        :param pos: position of the first chain
        :type pos: int
        :param len: number of chains to be inserted (if positive) or removed (if negative)
        :type len: int
        """

        select = lambda pid: pid[0] >= pos  # select all chains at or above pos
        adjust = lambda pid: (pid[0] + len, *pid[1:])
        self._modify_pad_ids(select, adjust)

    def remove_chains(self, chains):
        """insert/delete contiguous chains from fg

        :param chains: positions of the chains that are removed
        :type chains: seq(int)
        """

        if not len(chains):
            return  # nothing to remove

        chains = list(enumerate(sorted(set(chains))))[::-1]

        def adj(pid):
            return (
                pid[0] - next((i + 1 for i, v in chains if v < pid[0]), 0),
                *pid[1:],
            )

        select = lambda pid: pid[0] >= chains[0][1]  # select all chains at or above pos
        self._modify_pad_ids(select, adj)

    def merge_chains(self, id, to_id, to_len):
        """adjust link definitions when 2 internal chains are joined

        :param id: id of the chain to be moved
        :type id: int
        :param to_id: id of the chain to append to
        :type to_id: int
        :param to_len: length of the src chain
        :type to_len: int

        * all chain_id's >= id are affected
        * Graph is responsible to remove the connecting labels before running
          this function.
        """

        adjust = lambda pid: (to_id, pid[1] + to_len, pid[2])
        select = lambda pid: pid[0] == id
        self._modify_pad_ids(select, adjust)

    def adjust_filter_ids(self, cid, pos, len):
        """adjust filter id to insert another filter chain

        :param cid: target chain position in fg
        :type cid: int
        :param pos: filter position to insert another chain
        :type pos: int
        :param len: length of the chain to be inserted
        :type len: int
        """
        select = lambda pid: pid[0] == cid and pid[1] >= pos
        adjust = lambda pid: (pid[0], pid[1] + len, pid[2])
        self._modify_pad_ids(select, adjust)

    def del_chain(self, cid):
        """delete all links involving specified chain

        :param cid: chain id
        :type cid: int
        """

        def inspect(dst, src):

            if src and src[0] == cid:
                # delete if source chain is deleted
                return False

            if dst is not None:
                dsts = tuple((d for d in self.iter_dst_ids(dst, True)))
                new_dsts = tuple((d for d in dsts if d is None or d[0] != cid))
                n = len(new_dsts)
                return (
                    dst  # no change
                    if len(dsts) == n
                    else False  # all dsts with cid
                    if not n
                    else new_dsts[0]  # only 1 survived (the other was from cid)
                    if n == 1
                    else new_dsts  # mutiple survived
                )

            return True  # output label, not from cid

        self.data = {
            label: (dst, src)
            for label, dst, src in (
                (label, inspect(dst, src), src)
                for label, (dst, src) in self.data.items()
            )
            if dst is not False
        }
