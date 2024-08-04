import re
from collections import UserDict
from collections.abc import Generator, Mapping, Sequence, Callable


from ..utils import is_stream_spec
from ..errors import FFmpegioError
from .typing import PAD_INDEX

"""

Filtergraph Link Rules:
- One-to-one connection between an output pad of a filter to an input pad of another filter
- Multiple input pad may be connected to a same input stream
- Output labels must be unique, no duplicates

GraphLinks class design:
- Organize the links as a ``dict[str, tuple[PAD_INDEX|list[PAD_INDEX]|None,PAD_INDEX|None]]``
- key: link label, value=(``inpad``, ``output``): a tuple of the linked input and output pad indices
- If label is an input stream and links to input pads, ``inpad`` maybe a list of input pad and, 
  ``outpad`` is always ``None``
- To represent a link is not yet connected, ``inpad`` or ``outpad`` may be ``None`` but not both
  at the same time

"""


class GraphLinks(UserDict):

    class Error(FFmpegioError):
        pass

    @staticmethod
    def iter_inpad_ids(inpads, include_labels=False):
        """helper generator to work inpads ids

        :param inpads: inpads pad id or ids
        :type inpads: tuple(int,int,int) | seq(tuple(int,int,int)) | None
        :param include_labels: True to yield None for each unconnected labels, defaults to False to skip None inpads
        :param include_labels: bool, optional
        :yield: individual inpad id, immediately exits if None
        :rtype: tuple(int,int,int)|None
        """

        if inpads is None:
            if include_labels:
                yield inpads
        elif isinstance(inpads[0], int):
            yield inpads
        else:
            for inpad in inpads:
                if not (inpads is None and include_labels):
                    yield inpad

    @staticmethod
    def validate_label(label, named_only=False, no_stream_spec=False):
        try:
            assert re.match(r"[a-zA-Z0-9_]+$", label) or (
                not no_stream_spec and is_stream_spec(label)
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
                f"Link value must be a 2-element tuple with inpad and outpad pad ids"
            )

        (inpad, outpad) = ids
        GraphLinks.validate_pad_id(outpad)

        i = -1
        for i, d in enumerate(GraphLinks.iter_inpad_ids(inpad, True)):
            if d is None and outpad is None:
                raise GraphLinks.Error(f"multi-id input label item cannot be None.")
            GraphLinks.validate_pad_id(d)
        nel = i + 1

        if outpad is None and nel == 0:
            raise GraphLinks.Error(f"both outpad and inpad cannot be None.")

        if inpad is not None and not isinstance(inpad[0], int) and nel < 2:
            raise GraphLinks.Error(
                f"multi-id inpad link item must define more than 1 element."
            )

    @staticmethod
    def validate_item(label, pads):
        GraphLinks.validate_pad_id_pair(pads)  # this fails if None-None pair

        GraphLinks.validate_label(label, no_stream_spec=pads[1] is not None)

        # stream specifier can only be used as input label
        if is_stream_spec(label) and pads[1] is not None:
            raise GraphLinks.Error(
                f"Input stream specifier ({label}) can only be used as an input label."
            )

        # unnamed link cannot be a pad label
        if isinstance(label, int) and (
            not len(list(GraphLinks.iter_inpad_ids(pads[0]))) or pads[1] is None
        ):
            raise GraphLinks.Error(
                f"Unnamed (integer) links must specify both inpad and outpad."
            )

    @staticmethod
    def validate(data):

        inpads = set()  # inpad cannot be repeated

        # validate each link
        for label, pads in data.items():
            GraphLinks.validate_item(label, pads)
            for d in GraphLinks.iter_inpad_ids(pads[0]):
                # inpad pad id must be unique
                if d in inpads:
                    raise GraphLinks.Error(
                        f"Duplicate entries of inpad pad id {d} found (must be unique)"
                    )
                if d is not None:
                    inpads.add(d)

    @staticmethod
    def format_value(inpads, outpad, modifier=None):

        if modifier:
            if outpad is not None:
                outpad = modifier(outpad)
            modified = tuple(
                (
                    d if d is None else modifier(d)
                    for d in GraphLinks.iter_inpad_ids(inpads, True)
                )
            )
            n = len(modified)
            inpads = None if n < 1 else modified[0] if n < 2 else modified
        elif inpads is not None and isinstance(inpads[0], tuple):
            # make sure inpads sequence of ids is a tuple
            inpads = tuple(inpads)

        return (inpads, outpad)

    # regex pattern to identify a label with a trailing number
    LabelPattern = re.compile(r"(.+?)(\d+)?$")

    def __init__(self, links=None):
        # validate input arg
        if not isinstance(links, (GraphLinks, type(None))):
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

    def link(
        self,
        inpad: PAD_INDEX,
        outpad: PAD_INDEX,
        label: str | None = None,
        preserve_src_label: bool = False,
        force: bool = False,
    ) -> str | int:
        """set a filtergraph link

        :param inpad: input pad ids
        :param outpad: output pad id
        :param label: desired label name, defaults to None (=reuse inpad/outpad label or unnamed link)
        :param preserve_src_label: True to keep existing output labels of outpad, defaults to False
                                   to remove one output label of the outpad
        :param force: True to drop conflicting existing link, defaults to False
        :return: assigned label of the created link. Unnamed links gets a
                 unique integer value assigned to it.

        notes:
        - Unless `force=True`, inpad pad must not be already connected
        - User-supplied label name is a suggested name, and the function could
          modify the name to maintain integrity.
        - If inpad or outpad were previously named, their names will be dropped
          unless one matches the user-supplied label.
        - No guarantee on consistency of the link label (both named and unnamed)
          during the life of the object

        """

        # check if inpad already exists and resolve conflict if there is one
        in_label = self.find_inpad_label(inpad)
        if in_label is not None:
            if not (force or self.is_input(in_label)):
                raise GraphLinks.Error(f"input pad {inpad} already linked.")
            if force or isinstance(self.data[in_label][0][0], tuple):
                # if in_label has multi-inpads, cannot reuse it
                self.unlink(inpad=inpad)
                in_label = None

        # check if output label already exists. pick the first match
        out_label = (
            None
            if preserve_src_label
            else next(
                (k for k, (d, s) in self.data.items() if d is None and s == outpad),
                None,
            )
        )

        # finalize the label name
        # if not defined by user, select new label to be inpad or outpad label if found
        label = (
            label
            or (isinstance(in_label, str) and in_label)
            or (isinstance(out_label, str) and out_label)
            or None
        )

        if not (in_label or out_label):
            # new label, register
            label = self._register_label(label)

        # if input label was found to be updated, remove it
        if in_label is not None and label != in_label:
            # remove output label
            self.unlink(label=in_label)

        # if output label was found to be updated, remove it
        if out_label is not None and label != out_label:
            # remove output label
            self.unlink(label=out_label)

        # create the new link
        self.data[label] = (inpad, outpad)

        return label

    def unlink(self, label=None, inpad=None, outpad=None):
        """unlink specified links

        :param label: specify all the links with this label, defaults to None
        :type label: str|int, optional
        :param inpad: specify the link with this inpad pad, defaults to None
        :type inpad: tuple(int,int,int), optional
        :param outpad: specify all the links with this outpad pad, defaults to None
        :type outpad: tuple(int,int,int), optional
        """
        if label is not None:
            del self.data[label]
        if outpad is not None:
            for label in self.find_outpad_label(outpad):
                del self.data[label]
        if inpad is not None:
            label = self.find_inpad_label(inpad)
            inpads, outpad = self.data[label]
            if isinstance(inpads[0], int):  # unique label
                del self.data[label]
            else:  # multi-inpads label
                # depends on how many left
                inpads = tuple((d for d in inpads if d != inpad))
                self.data[label] = (
                    (inpads, outpad) if len(inpads) > 1 else (inpads[0], outpad)
                )

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

        if is_stream_spec(label):
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
        """get link item by label or by inpad pad id tuple

        :param key: label name or inpad pad id tuple (int,int,int)
        :type key: str or tuple(int,int,int)
        :return: link inpads-outpad pair
        :rtype: tuple(tuple(tuple(int,int,int))|None,tuple(int,int,int)|None)
        """
        try:
            # try as label first
            return super().__getitem__(key)
        except Exception as e:
            # try as inpad id
            label = self.find_inpad_label(key)
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

        If multi-inpad label, True if any inpad is not None
        """
        lnk = self.data.get(label, (None, None))
        return lnk[1] is not None and any(self.iter_inpad_ids(lnk[0]))

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

        If multi-inpad label, True if any inpad is None
        """
        lnk = self.data.get(label, None)
        return lnk and any((d is None for d in self.iter_inpad_ids(lnk[0], True)))

    def num_outputs(self, label):
        """Get number of outputs

        :param label: link label
        :type label: str
        :return: number of output (logical) pads
        :rtype: int

        If multi-inpad label, True if any inpad is None
        """
        lnk = self.data.get(label, None)
        return int(lnk is not None) and sum(
            (d is None for d in self.iter_inpad_ids(lnk[0], True))
        )

    def iter_input_pads(
        self, label: str | None = None
    ) -> Generator[str, PAD_INDEX, PAD_INDEX | None]:
        """Iterate over all link elements, possibly separating inpad ids with
           the same label

        :param label: to iterate only on this label, defaults to None (all frames)
        :type label: str, optional
        :yield: a full link definition (inpad or outpad may be None if input or output label, respectively)
        :rtype: tuple of label, inpad id, and outpad id
        """

        def iter(label, inpad, outpad):
            for d in self.iter_inpad_ids(inpad, True):
                yield (label, d, outpad)

        if label is None:
            for label, (inpad, outpad) in self.data.items():
                for v in iter(label, inpad, outpad):
                    yield v
        else:
            for v in iter(label, *self.data[label]):
                yield v

    def iter_links(
        self, label: str | None = None, include_input_stream: bool = False
    ) -> Generator[tuple[str, PAD_INDEX, PAD_INDEX | None]]:
        """Iterate over only actual links, separating inpad ids with
           the same input stream

        :param label: to iterate only on this label, defaults to None (all frames)
        :param include_input_stream: True to include input pads connected to input streams.
        :yield: label, input pad, and output pad of a link
        """

        def iter(label, inpad, outpad):
            if outpad is not None or (include_input_stream and is_stream_spec(label)):
                for d in self.iter_inpad_ids(inpad):
                    yield (label, d, outpad)

        if label is None:
            for label, (inpad, outpad) in self.data.items():
                for v in iter(label, inpad, outpad):
                    yield v
        else:
            for v in iter(label, *self.data[label]):
                yield v

    def iter_inputs(
        self, exclude_stream_specs: bool = True
    ) -> Generator[tuple[str, PAD_INDEX]]:
        """Iterate over only input labels, possibly repeating the same label if shared among
           multiple input pad ids

        :param exclude_stream_specs: True to not include input streams
        :yield: label and pad index
        """
        for label, (inpad, outpad) in self.data.items():
            if outpad is None and not (exclude_stream_specs and is_stream_spec(label)):
                for d in self.iter_inpad_ids(inpad):
                    yield (label, d)

    def iter_input_streams(self) -> Generator[tuple[str, PAD_INDEX]]:
        """Iterate over input stream labels, possibly repeating the same label if shared among
           multiple input pad ids

        :yield: label and pad index
        """
        for label, (inpad, outpad) in self.data.items():
            if outpad is None and is_stream_spec(label):
                for d in self.iter_inpad_ids(inpad):
                    yield (label, d)

    def iter_outputs(self) -> Generator[tuple[str, PAD_INDEX]]:
        """Iterate over only output labels

        :yield: a full output definition
        """

        # iterate over all labels
        for label, (inpad, outpad) in self.data.items():
            if inpad is None:
                yield (label, outpad)

    def input_dict(self) -> dict[PAD_INDEX, PAD_INDEX | str]:
        """Return the link table sorted by the input pad indices

        The value of the returned dict is either the connected output pad index
        if linked or a string if input pad is unconnected. Unconnected output
        labels are excluded in the returned dict.

        :see also:
        ``Graph.iter_input_pads``
        """

        return {
            d: label if outpad is None else outpad
            for label, (inpad, outpad) in self.data.items()
            if inpad is not None
            for d in self.iter_inpad_ids(inpad)
        }

    def output_dict(self) -> dict[PAD_INDEX, PAD_INDEX | str]:
        """return the link table sorted by the output pad indices

        The value of the returned dict is either the connected input pad index
        if linked or a label string if unconnected labels. Unconnected input
        labels are excluded in the returned dict.
        """

        return {
            outpad: label if inpad is None else inpad
            for label, (inpad, outpad) in self.data.items()
            if outpad is not None
        }

    def find_inpad_label(self, inpad: PAD_INDEX) -> str | None:
        """get label of an input pad id

        :param inpad: input filter pad id
        :return: found label or None if no match found
        """
        try:
            return next(
                (label for label, dst1, _ in self.iter_input_pads() if inpad == dst1),
                None,
            )
        except StopIteration:
            return None

    def find_outpad_label(self, outpad: PAD_INDEX) -> str | None:
        """get labels of a source/output pad id

        :param inpad: output filter pad id
        :return: found label or None if outpad is None
        """
        try:
            return next(
                label for label, (_, src1) in self.data.items() if outpad == src1
            )
        except StopIteration:
            return None

    def find_link_label(self, inpad, outpad):
        if outpad is None or inpad is None:
            return None
        return next(
            (l for l, d, s in self.iter_links() if outpad == s and inpad == d), None
        )

    def are_linked(
        self,
        inpad: PAD_INDEX | None,
        outpad: PAD_INDEX | None,
        check_input_stream: bool | str = False,
    ) -> bool:
        """True if given pads are linked

        :param inpad: input pad index, default to ``None`` to check if ``outpad`` is connected to any
                      input pad.
        :param outpad: output pad index, defaults to ``None`` to check if ``inpad`` is connected to any
                       output pad or an input stream.
        :param check_input_stream: True to check inpad is connected to an input stream, or a stream
                                   specifier string to check the connection to a specific stream, defaults
                                   to ``False``.

        ``ValueError`` will be raised if both ``inpad`` and ``outpad`` ``None`` or
        if ``include_input_stream!=False`` and ``outpad`` is ``None``.

        """

        if isinstance(check_input_stream, str):
            # check for a specific input stream
            if outpad is not None:
                raise ValueError(
                    f"Both {outpad=} and {check_input_stream=} cannot be specified at the same time."
                )
            return any(
                inpad == d for _, d, _ in self.iter_input_pads(check_input_stream)
            )
        else:
            if inpad is None and outpad is None:
                raise ValueError(f"At least one of inpad or outpad must be specified.")

            # check internal links first
            it_links = self.iter_links()

            # single check for a specific outpad
            if outpad is not None:
                return any(
                    (outpad == s for _, _, s in it_links)
                    if inpad is None
                    else (outpad == s and inpad == d for _, d, s in it_links)
                )

            # possible 2-step check for an arbitrary ouput

            # first check internal links
            res = any(inpad == d for _, d, _ in it_links)
            # then check for input stream if no link was found
            return (
                any(inpad == d for _, d in self.iter_input_streams())
                if check_input_stream and not res and outpad is None
                else res
            )

    def create_label(self, label, inpad=None, outpad=None, force=None):
        """label a filter pad

        :param label: name of the new label or input stream specifier (for input label only)
        :type label: str
        :param inpad: input filter pad id (or a sequence of ids), defaults to None
        :type inpad: tuple(int,int,int) or seq(tuple(int,int,int)), optional
        :param outpad: output filter pad id, defaults to None
        :type outpad: tuple(int,int,int), optional
        :param force: True to delete existing labels, defaults to None
        :type force: bool, optional
        :return: actual label name
        :rtype: str

        Only one of inpad and outpad argument must be given.

        If given label already exists, no new label will be created.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        if (outpad is None) == (inpad is None):
            raise ValueError("outpad or inpad (but not both) must be given.")

        # check if inpad already exists and resolve conflict if there is one
        if inpad:
            inpads = [inpad] if isinstance(inpad, tuple) else inpad

            # get labels of outpad and inpad if already exists
            dst_labels = set(
                (d for d in (self.find_inpad_label(d) for d in inpads) if d is not None)
            )

            # already labeled as specified
            if len(dst_labels) == 1 and label in dst_labels:
                return label

            # if an unmatched labal is already assigned to inpad
            if len(dst_labels):
                if force:
                    # drop existing if forced
                    for d in inpads:
                        self.unlink(inpad=d)
                else:
                    # or throw an error
                    raise GraphLinks.Error(f"the input pad(s) {inpad} already linked.")

            if not isinstance(inpad, tuple):
                inpad = tuple(inpad)

        else:
            if is_stream_spec(label):
                raise GraphLinks.Error(
                    f"the output label [{label}] cannot be a stream specifier."
                )

            if label in self.find_outpad_label(outpad):
                # already labeled as specified
                return label

        # create the link
        label = self._register_label(label)
        self.data[label] = (inpad, outpad)
        return label

    def remove_label(self, label, inpad=None):
        """remove an input/output label

        :param label: unconnected link label
        :type label: str
        :param inpad: (multi-input label only) specify the input filter pad id
        :type inpad: int, optional

        Removing an input label by default removes all associated filter pad ids
        unless `inpad` is specified.

        """
        try:
            inpads, outpad = self.data[label]
        except:
            raise GraphLinks.Error(f"{label} is not a valid link label.")

        if inpads is None or (outpad is None and inpad is None):
            # simple in/out label
            del self.data[label]
        else:
            # possible for an output label coexisting with link labels
            inpads = tuple(self.iter_inpad_ids(inpads, True))
            new_dsts = tuple(
                (d for d in inpads if d is not None)
                if inpad is None
                else (d for d in inpads if d is not None and d != inpad)
            )
            n = len(new_dsts)
            if n == len(inpads):
                raise GraphLinks.Error(
                    f"no specified input labels found: {label} (inpad={inpad})."
                )

            if n < 1:
                del self.data[label]
            else:
                self.data[label] = (
                    (new_dsts[0], outpad) if n < 2 else (new_dsts, outpad)
                )

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
        :param force: True to overwrite existing link inpad id, defaults to False
        :type force: bool, optional
        :returns: dict of given key to the actual labels assigned
        :rtype: dict
        """
        if not isinstance(other, GraphLinks):
            try:
                assert isinstance(other, Mapping)
            except Exception as e:
                raise GraphLinks.Error(f"Other must be a dict-like mapping object")
            self.validate(other)

        n = len(other)
        if not n:
            return {}

        # set chain index adjustment function if offset given
        adj_fn = (lambda id: (id[0] + offset, *id[1:])) if offset else None

        # prep other's inpads value (adjust chain id & check for duplicate)
        to_unlink = []  # for forcing inpad

        def chk_dst(d, do):
            if any((d == d0 for _, d0, _ in self.iter_input_pads())):
                if force:
                    to_unlink.append(d)
                else:
                    raise GraphLinks.Error(
                        f"inpad id {do} with chain id offset {offset or 0} conflicts with existing inpad "
                    )

        def prep_ids(inpads, outpad):
            dsts_adj, outpad = (
                self.format_value(inpads, outpad, adj_fn)
                if offset
                else (inpads, outpad)
            )
            if inpads is not None:
                if isinstance(inpads[0], int):
                    chk_dst(dsts_adj, inpads)
                else:
                    for d, d0 in zip(dsts_adj, inpads):
                        chk_dst(d, d0)
            return dsts_adj, outpad

        other = [(k, prep_ids(*v)) for k, v in other.items()]

        # delete inpads to be overwritten
        for inpad in to_unlink:
            self.unlink(inpad=inpad)

        # process each input item
        def process_item(label, inpads, outpad):
            new_label = True
            if label in self.data:
                dsts_self, src_self = self.data[label]
                if auto_link:
                    # try to link matching input & output pads
                    if inpads is None and src_self is None:
                        self.data[label] = (dsts_self, outpad)
                        return label
                    elif outpad is None and dsts_self is None:
                        self.data[label] = (inpads, src_self)
                        return label

                if outpad == src_self:
                    # if links from the same source, merge
                    inpads = tuple(
                        (
                            *self.iter_inpad_ids(dsts_self, True),
                            *self.iter_inpad_ids(inpads, True),
                        )
                    )
                    new_label = False

            if new_label:
                label = self._register_label(label)
            self.data[label] = (inpads, outpad)
            return label

        return {
            label: process_item(label, inpads, outpad)
            for label, (inpads, outpad) in other
        }

    def get_repeated_outpad_info(self):
        """return a nested dict with an item per multi-destination filter output pad id's.

        :return: dict of multi-destination srcs
        :rtype: dict

        { filter output pad id: {
            output link label : None
            filter input pad id: link label
        }}
        """
        # iterate all the sources with multiple destinations
        # dict(key=outpad id: value=dict(key=inpad id|None: value=label|# of output labels))

        # gather all sources, rename labels to guarantee uniqueness
        srcs = {}
        for label, (inpads, outpad) in self.data.items():
            if outpad is None:
                continue
            if outpad in srcs:
                item = srcs[outpad]
            else:
                item = srcs[outpad] = {}

            inpads = tuple(self.iter_inpad_ids(inpads, True))
            if len(inpads) > 1:
                item.update({f"{label}_{i}": inpad for i, inpad in enumerate(inpads)})
            else:
                item[label] = inpads[0]

        # drop all sources with single-destination
        return {outpad: inpads for outpad, inpads in srcs.items() if len(inpads) > 1}

    def _modify_pad_ids(self, select: Callable, adjust: Callable):
        """generic pad id modifier

        :param select: function to select a pad id to modify: select(id)->bool
        :param adjust: function to adjust the selected pad id: adjust(id)->new_id

        """

        def adjust_pair(inpads, outpad):
            if outpad is not None and select(outpad):
                outpad = adjust(outpad)
            if inpads is not None:
                if isinstance(inpads[0], int):
                    if select(inpads):
                        inpads = adjust(inpads)
                else:
                    inpads = tuple(adjust(d) if select(d) else d for d in inpads)
            return (inpads, outpad)

        self.data = {label: adjust_pair(*value) for label, value in self.data.items()}

    def adjust_chains(self, pos: int, len: int):
        """insert/delete contiguous chains from fg

        :param pos: position of the first chain
        :param len: number of chains to be inserted (if positive) or removed (if negative)
        """

        select = lambda pid: pid[0] >= pos  # select all chains at or above pos
        adjust = lambda pid: (pid[0] + len, *pid[1:])
        self._modify_pad_ids(select, adjust)

    def remove_chains(self, chains: Sequence[int]):
        """insert/delete contiguous chains from fg

        :param chains: positions of the chains that are removed
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

    def merge_chains(self, id: int, to_id: int, to_len: int):
        """adjust link definitions when 2 internal chains are joined

        :param id: id of the chain to be moved
        :param to_id: id of the chain to append to
        :param to_len: length of the outpad chain

        * all chain_id's >= id are affected
        * Graph is responsible to remove the connecting labels before running
          this function.
        """

        adjust = lambda pid: (to_id, pid[1] + to_len, pid[2])
        select = lambda pid: pid[0] == id
        self._modify_pad_ids(select, adjust)

    def adjust_filter_ids(self, cid: int, pos: int, len: int):
        """adjust filter id to insert another filter chain

        :param cid: target chain position in fg
        :param pos: filter position to insert another chain
        :param len: length of the chain to be inserted
        """
        select = lambda pid: pid[0] == cid and pid[1] >= pos
        adjust = lambda pid: (pid[0], pid[1] + len, pid[2])
        self._modify_pad_ids(select, adjust)

    def del_chain(self, cid: int):
        """delete all links involving specified chain

        :param cid: chain id
        """

        def inspect(inpad, outpad):

            if outpad and outpad[0] == cid:
                # delete if source chain is deleted
                return False

            if inpad is not None:
                inpads = tuple((d for d in self.iter_inpad_ids(inpad, True)))
                new_dsts = tuple((d for d in inpads if d is None or d[0] != cid))
                n = len(new_dsts)
                return (
                    inpad  # no change
                    if len(inpads) == n
                    else (
                        False  # all inpads with cid
                        if not n
                        else (
                            new_dsts[0]  # only 1 survived (the other was from cid)
                            if n == 1
                            else new_dsts
                        )
                    )  # mutiple survived
                )

            return True  # output label, not from cid

        self.data = {
            label: (inpad, outpad)
            for label, inpad, outpad in (
                (label, inspect(inpad, outpad), outpad)
                for label, (inpad, outpad) in self.data.items()
            )
            if inpad is not False
        }
