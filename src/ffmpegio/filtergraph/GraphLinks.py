from __future__ import annotations

import re
from collections import UserDict, defaultdict
from collections.abc import Callable, Generator, Mapping, Sequence

from typing_extensions import Literal, cast

from ..errors import FFmpegioError
from ..stream_spec import is_map_option
from .typing import PAD_INDEX, PAD_PAIR

PAD_INDEX_ = tuple[int, int, int]
"""proper pad index, exclusively used in GraphLinks    """

PAD_PAIR = tuple[PAD_INDEX | tuple[PAD_INDEX], PAD_INDEX]
"""user-provided pad index pair

    A tuple pair of (input pad index, output pad index). The first item, 
    input pad index, may be a tuple of pad indices ONLY when the associated
    label is an input stream.    

    Only one of input or output pad maybe ``None``, indicating the associated
    pad label is an input/output label.

    Unlike ``PAD_PAIR_`` the pad indices in this tuple may contain a partial pad
    index.
    """


PAD_PAIR_ = tuple[PAD_INDEX_ | tuple[PAD_INDEX_] | None, PAD_INDEX_ | None]
"""concrete pad index pair mapped to every filter pad label

    A tuple pair of (input pad index, output pad index). The first item, 
    input pad index, may be a tuple of pad indices ONLY when the associated
    label is an input stream.    

    Only one of input or output pad maybe ``None``, indicating the associated
    pad label is an input/output label.

    """

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
    def iter_inpad_ids(
        inpads: PAD_INDEX | list[PAD_INDEX] | None, include_labels: bool = False
    ) -> Generator[PAD_INDEX]:
        """helper generator to work inpads ids

        :param inpads: inpads pad id or ids
        :param include_labels: True to yield None for each unconnected labels, defaults to False to skip None inpads
        :param include_labels: bool, optional
        :yield: individual inpad id, immediately exits if None
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
    def validate_label(label: str | int, is_link: bool | None = None) -> str | int:

        if isinstance(label, int):
            if is_link is False:
                raise GraphLinks.Error(
                    "A pad label without a link must be a string label."
                )
        elif isinstance(label, str) and len(label):
            # remove the square bracket if present
            if label[0] == "[" and label[-1] == "]":
                label = label[1:-1]

            if not re.match(r"[a-zA-Z0-9_]+$", label):
                raise GraphLinks.Error(
                    "Pad label must be a string of alphanumeric characters and '_'"
                )
        else:
            raise GraphLinks.Error(
                f"{type(label)} is not a supported pad label data type"
            )

        return label

    @staticmethod
    def validate_input_stream(label: str) -> bool:

        if not isinstance(label, str):
            raise GraphLinks.Error(
                "Input stream specifier must be an input stream specifier."
            )
        elif isinstance(label, str) and len(label):
            # remove the square bracket if present
            if label[0] == "[" and label[-1] == "]":
                label = label[1:-1]

            # check for input stream specifier
            if not is_map_option(label, allow_missing_file_id=True):
                raise GraphLinks.Error("Pad label is not an input stream specifier.")

        return label

    @staticmethod
    def validate_pad_idx(
        index: PAD_INDEX | None,
        none_ok: bool = False,
        default_chain_pos: int = 0,
        default_filter_pos: int = 0,
    ) -> PAD_INDEX_:

        if index is None:
            if none_ok:
                return
            raise GraphLinks.Error("pad index cannot be None")

        if isinstance(index, int):
            values = [None, None, index]
        else:
            try:
                n = len(index)
                assert (
                    n > 0
                    and n <= 3
                    and all(
                        (isinstance(pos, int) and pos >= 0) or (pos is None and none_ok)
                        for pos in index
                    )
                )
            except (TypeError, AssertionError) as e:
                raise GraphLinks.Error(
                    "pad index must be a nonnegative int or a sequence of up to 3 ints"
                ) from e

            if n == 1:
                values = [None, None, *index]
            elif n == 2:
                values = [None, *index]
            else:
                values = [*index]

        if not none_ok:
            if values[2] is None:
                raise GraphLinks.Error("filter pad position cannot be None")

            # use chain and filter default positions if not provided
            for i, default in enumerate((default_chain_pos, default_filter_pos, None)):
                pos = values[i]
                if pos is None:
                    values[i] = default

        return (*values,)

    @staticmethod
    def validate_pad_idx_pair(
        ids: tuple[PAD_INDEX | Sequence[PAD_INDEX] | None, PAD_INDEX | None],
        none_pos_ok: bool = False,
        default_chain_pos: int = 0,
        default_filter_pos: int = 0,
    ) -> tuple[PAD_INDEX_ | tuple[PAD_INDEX_] | None, PAD_INDEX_ | None]:

        try:
            assert len(ids) == 2
        except (TypeError, AssertionError):
            raise GraphLinks.Error("Link index pair must be a 2-element sequence.")

        (inpad, outpad) = ids

        if inpad is None and outpad is None:
            raise GraphLinks.Error("Both input and output pads cannot be None.")

        if inpad is not None:
            try:
                # try pad index first
                inpad = GraphLinks.validate_pad_idx(
                    inpad, none_pos_ok, default_chain_pos, default_filter_pos
                )
            except GraphLinks.Error:
                # if failed, try as a sequence of pad indices (linking to an input stream)
                inpad = tuple(
                    GraphLinks.validate_pad_idx(
                        item, False, default_chain_pos, default_filter_pos
                    )
                    for item in inpad
                )

                if len(inpad) == 0:
                    raise GraphLinks.Error(
                        "At least one input pad must be connected to an input stream."
                    )

        if outpad is not None:
            outpad = GraphLinks.validate_pad_idx(
                outpad, none_pos_ok, default_chain_pos, default_filter_pos
            )

        return inpad, outpad

    @staticmethod
    def validate_item(
        label: str | int | None,
        pads: PAD_PAIR,
        none_label_ok: bool = False,
        item_type: Literal["link", "label"] | None = None,
        default_chain_pos: int = 0,
        default_filter_pos: int = 0,
    ) -> tuple[str | int | None, PAD_PAIR_]:
        """validate and format a graph link pair of a label and a pair of pads

        :param label: link label or ``None`` to be auto-numbered
        :param pads: input-output pad pair. One of the pad may be ``None`` to
            specify an input/output label. If ``label`` is an input stream
            specifier string, multiple input pads may be provided with output
            pad as ``None``.
        :param none_label_ok: ``True`` to allow ``label`` to be ``None``,
            defaults to ``False``
        :param link_only: ``True`` to raise an exception if the item is not a
            link
        :param label_only: ``True`` to raise an exception if the item is a
            link
        :param default_chain_pos: default chain position to use if chain
            position is missing in a pad index, defaults to 0
        :param default_filter_pos: default filter position to use if filter
            position is missing in a pad index, defaults to 0
        :return: input label and pads with the latter in a tuple-only format
        """

        if item_type is None:
            item_type = "label" if any(pad is None for pad in pads) else "link"

        return (
            GraphLinks.validate_link_item(
                label, pads, none_label_ok, default_chain_pos, default_filter_pos
            )
            if item_type == "link"
            else GraphLinks.validate_label_item(
                label, pads, default_chain_pos, default_filter_pos
            )
        )

    @staticmethod
    def validate_link_item(
        label: str | int | None,
        pads: PAD_PAIR,
        none_label_ok: bool = False,
        default_chain_pos: int = 0,
        default_filter_pos: int = 0,
    ) -> tuple[str | int | None, PAD_PAIR_]:
        """validate and format a graph link pair of a label and a pair of pads

        :param label: link label or ``None`` to be auto-numbered
        :param pads: input-output pad pair. One of the pad may be ``None`` to
            specify an input/output label. If ``label`` is an input stream
            specifier string, multiple input pads may be provided with output
            pad as ``None``.
        :param none_label_ok: ``True`` to allow ``label`` to be ``None``,
            defaults to ``False``
        :param link_only: ``True`` to raise an exception if the item is not a
            link
        :param label_only: ``True`` to raise an exception if the item is a
            link
        :param default_chain_pos: default chain position to use if chain
            position is missing in a pad index, defaults to 0
        :param default_filter_pos: default filter position to use if filter
            position is missing in a pad index, defaults to 0
        :return: input label and pads with the latter in a tuple-only format
        """

        if label is None:
            if not none_label_ok:
                raise GraphLinks.Error("label cannot be None.")
        else:
            # check label and whether it can be an input stream specifier
            label = GraphLinks.validate_label(label, is_link=True)

        # check the pad pair
        inpad, outpad = GraphLinks.validate_pad_idx_pair(
            pads, False, default_chain_pos, default_filter_pos
        )

        if inpad is None or outpad is None or isinstance(inpad[0], tuple):
            raise GraphLinks.Error(
                "a link item must specify one-to-one output to input connection."
            )

        return label, (inpad, outpad)

    @staticmethod
    def validate_label_item(
        label: str | int | None,
        pads: PAD_PAIR,
        default_chain_pos: int = 0,
        default_filter_pos: int = 0,
    ) -> tuple[str, PAD_PAIR_]:
        """validate and format a graph link pair of a label and a pair of pads

        :param label: link label or ``None`` to be auto-numbered
        :param pads: input-output pad pair. One of the pad may be ``None`` to
            specify an input/output label. If ``label`` is an input stream
            specifier string, multiple input pads may be provided with output
            pad as ``None``.
        :param none_label_ok: ``True`` to allow ``label`` to be ``None``,
            defaults to ``False``
        :param link_only: ``True`` to raise an exception if the item is not a
            link
        :param label_only: ``True`` to raise an exception if the item is a
            link
        :param default_chain_pos: default chain position to use if chain
            position is missing in a pad index, defaults to 0
        :param default_filter_pos: default filter position to use if filter
            position is missing in a pad index, defaults to 0
        :return: input label and pads with the latter in a tuple-only format
        """

        if not isinstance(label, str):
            raise GraphLinks.Error("label must be a string.")

        # check label and whether it can be an input stream specifier
        try:
            label_ = GraphLinks.validate_input_stream(label)
        except GraphLinks.Error:
            label_ = GraphLinks.validate_label(label, is_link=False)
            is_stream_spec = False
        else:
            is_stream_spec = True

        # check the pad pair
        inpad, outpad = GraphLinks.validate_pad_idx_pair(
            pads, False, default_chain_pos, default_filter_pos
        )

        if (inpad is None) and (outpad is None):
            raise GraphLinks.Error(
                "Only one of input and output pads can be specified."
            )

        if inpad is None:
            if is_stream_spec and not re.match(r"[a-zA-Z0-9_]+$", label):
                raise GraphLinks.Error("ouput label cannot be a stream specifier")

            # output pad - completed
            return label_, (inpad, outpad)

        # input pad - check input stream specifier
        if is_stream_spec and isinstance(inpad[0], int):
            inpad = (inpad,)

        return label_, (inpad, outpad)

    @staticmethod
    def validate(
        data: dict[str | int, PAD_PAIR],
        default_chain_pos: int = 0,
        default_filter_pos: int = 0,
    ) -> dict[int | str, PAD_PAIR_]:
        """validate and format a user-defined GraphLinks compatible map

        :param data: user-defined map of pad labels and input and output pads
        :param default_chain_pos: default chain position to use if chain
            position is missing in a pad index, defaults to 0
        :param default_filter_pos: default filter position to use if filter
            position is missing in a pad index, defaults to 0
        :return: equivalent dict of ``data`` but its content are guaranteed to
            be used as ``GraphLinks`` items.
        """
        # pads must be unique for both input and output
        used_inpads = set()
        used_outpads = set()

        # validate each link
        out = {}
        for label, pad_pair in data.items():
            key, value = GraphLinks.validate_item(
                label,
                pad_pair,
                default_chain_pos=default_chain_pos,
                default_filter_pos=default_filter_pos,
            )

            # check the uniqueness of input pads
            for pad in GraphLinks.iter_inpad_ids(value[0]):
                if pad in used_inpads:
                    raise GraphLinks.Error(
                        f"Input filter pad {value[0]} is used multiple times"
                    )
                used_inpads.add(pad)

            # check the uniqueness of output pads
            if value[1] in used_outpads:
                raise GraphLinks.Error(
                    f"Out filter pad {value[1]} is used multiple times"
                )
            if value[1] is not None:
                used_outpads.add(value[1])

            # all good, add to the formatted dict
            out[key] = value

        return out

    # regex pattern to identify a label with a trailing number
    AutoLabelPattern = re.compile(r"^L\d+?$")

    _auto_count: int = 0

    def __init__(
        self,
        links: dict[str | int, PAD_PAIR] | GraphLinks | None = None,
    ):

        # calls update() if links set
        super().__init__()

        # validate input arg
        if links is not None:
            if not isinstance(links, GraphLinks):
                links = self.validate(links)

            # re-number all int labels
            self.data = {
                k if isinstance(k, str) else self._auto_label(): v
                for k, v in links.items()
            }

    def _auto_label(self) -> int:
        i = self._auto_count
        self._auto_count = self._auto_count + 1
        return i

    def __getitem__(self, key: str | int) -> PAD_PAIR_:

        try:
            try:
                key_ = self.validate_label(key)
            except GraphLinks.Error:
                key_ = self.validate_input_stream(key)
        except GraphLinks.Error as e:
            raise KeyError("Unknown label") from e

        return super().__getitem__(key_)

    def __setitem__(self, key: str | int, value: PAD_PAIR):

        # can only set named key
        if value[0] is None:
            self.create_label(key, outpad=value[1], force=True)
        elif value[1] is None:
            self.create_label(key, inpad=value[0], force=True)
        else:
            self.link(value[0], value[1], label=key, force=True)

    def link(
        self,
        inpad: PAD_INDEX,
        outpad: PAD_INDEX,
        label: str | None = None,
        preserve_label: Literal[False, "input", "output"] = False,
        force: bool = False,
    ) -> str | int:
        """set a filtergraph link from outpad to inpad

        :param inpad: input pad ids
        :param outpad: output pad id
        :param label: desired label name, defaults to None (=reuse inpad/outpad
            label or unnamed link)
        :param preserve_label: ``False`` to remove the labels of the input and
            output pads (default) or ``'input'`` to prefer the input label or
            ``'output'`` to prefer the output label.
        :param force: ``True`` to drop conflicting existing link, defaults to
            ``False``
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

        label_, (inpad_, outpad_) = self.validate_link_item(
            None if isinstance(label, int) else label,
            (inpad, outpad),
            none_label_ok=True,
        )

        pads_to_unlink = []

        # check if inpad already exists and resolve conflict if there is one
        inlabel = self._is_inpad_used(inpad_)
        if inlabel is True:
            if not force:
                raise GraphLinks.Error(
                    f"The specified input pad {inpad} is already linked."
                )
            pads_to_unlink.append({"inpad": inpad_})
            inlabel = False
        elif inlabel is not False and self.is_input_stream(inlabel):
            if not (
                force
                or (len(self.data[inlabel][0]) == 1 and self.validate_label(inlabel))
            ):
                raise GraphLinks.Error(
                    "specified input pad is already connected to an input stream."
                )
            pads_to_unlink.append({"label": inlabel})
            inlabel = False

        # check if output label already exists. pick the first match
        outlabel = self._is_outpad_used(outpad_)
        if outlabel is True:
            if not force:
                raise GraphLinks.Error(
                    f"The specified output pad {outpad_} is already linked."
                )
            pads_to_unlink.append({"inpad": outpad_})
            outlabel = False

        if label_ in self and (label_ != inlabel and label_ != outlabel):
            if not force:
                raise GraphLinks.Error(
                    f"The specified label {label} is already in use."
                )
            pads_to_unlink.append({"label": label_})

        # good to proceed: unlink the existing pads/labels
        for kws in pads_to_unlink:
            self.unlink(**kws)

        # if label is not set, try to use input/output label if exists
        if label_ is None and preserve_label is not False:
            label_ = (
                outlabel if preserve_label == "output" or inlabel is None else inlabel
            )

        # new auto-label
        if not label_:
            label_ = self._auto_label()

        # create the new link (overwrite if forced)
        self.data[label_] = (inpad_, outpad_)

        return label_

    def create_label(
        self,
        label: str,
        inpad: PAD_INDEX | Sequence[PAD_INDEX] | None = None,
        outpad: PAD_INDEX | None = None,
        force: bool = False,
    ) -> str:
        """label a filter pad

        :param label: name of the new label or input stream specifier (for input label only)
        :param inpad: input filter pad id (or a sequence of ids), defaults to None
        :param outpad: output filter pad id, defaults to None
        :param force: True to delete existing labels, defaults to None
        :return: created label name

        Only one of inpad and outpad argument must be given.

        If given label already exists, no new label will be created.

        If label has a trailing number, the number will be dropped and replaced with an
        internally assigned label number.

        """

        label_, (inpad_, outpad_) = self.validate_label_item(label, (inpad, outpad))

        label_in_use = label_ in self

        pads_to_unlink = []

        if not force and label_in_use and not self.is_input_stream(label_):
            raise GraphLinks.Error(f"{label=} is already in use.")

        # make sure no input pad is already in use
        if inpad_ is not None:
            for pad in self.iter_inpad_ids(inpad_):
                inlabel = self._is_inpad_used(pad)
                if inlabel is True:
                    # pad is already connected
                    if force:
                        pads_to_unlink.append({"inpad": pad})
                    else:
                        raise GraphLinks.Error(f"input pad {pad} is already in use.")
                elif inlabel is not False and inlabel != label_:
                    # pad already has an input label
                    if force:  # or not self.is_input_stream(inlabel):
                        # allow renaming as long as not input stream
                        pads_to_unlink.append({"label": inlabel})
                    else:
                        raise GraphLinks.Error(
                            f"input pad {pad} is already connected to another input stream ({inlabel})."
                        )

        # make sure output pad is already in use
        if outpad_ is not None:
            outlabel = self._is_outpad_used(outpad_)
            if outlabel is True:
                # pad is already connected
                if force:
                    pads_to_unlink.append({"outpad": outpad_})
                else:
                    raise GraphLinks.Error(f"output pad {outpad_} is already in use.")

            elif outlabel is not False and outlabel != label_:
                # is an input label
                pads_to_unlink.append({"label": outlabel})

        # all good, remove existing items
        for cfg in pads_to_unlink:
            self.unlink(**cfg)

        if isinstance(inpad_, tuple) and label_ in self:
            # extend input stream specifier connections
            self.data[label_] = ((*self[label_][0], *inpad_), None)
        else:
            self.data[label_] = (inpad_, outpad_)

        return label_

    def link_by_labels(
        self,
        in_label: str,
        out_label: str,
        label: str | None = None,
        preserve_label: Literal[False, "input", "output"] = False,
    ) -> str | int:
        """set a filtergraph link from outpad to inpad

        :param in_label: input pad label
        :param out_label: output pad label
        :param label: desired new label name, defaults to None (=reuse inpad/outpad label or unnamed link)
        :param preserve_label: `False` to remove the labels of the input and output pads (default) or
                               `'input'` to prefer the input label or `'output'` to prefer the output
                               label.
        :return: assigned label of the created link. Unnamed links gets a
                 unique integer value assigned to it.

        """

        if not self.is_input(in_label, exclude_stream_specs=True):
            raise ValueError(f"{in_label=} is not a valid input label.")
        if not self.is_output(out_label):
            raise ValueError(f"{out_label=} is not a valid output label.")

        link_value = (self[in_label][0], self[out_label][1])

        linked = label is None
        if linked:
            if preserve_label == "input":
                label = in_label
                self[label] = link_value
                del self[out_label]
            elif preserve_label == "output":
                label = out_label
                self[label] = link_value
                del self[in_label]
            elif preserve_label is False:
                label = self._auto_label()
                linked = False
            else:
                raise ValueError(f"{preserve_label=} is not a valid value.")
        else:
            label = self.validate_label(label, is_link=True)

        # delete old labels and create a new link with the chosen label
        if not linked:
            del self[in_label]
            del self[out_label]
            self[label] = link_value

        return label

    def unlink(
        self,
        *,
        label: str | int | None = None,
        inpad: PAD_INDEX | None = None,
        outpad: PAD_INDEX | None = None,
    ):
        """unlink specified links

        :param label: specify all the links with this label, defaults to None
        :param inpad: specify the link with this inpad pad, defaults to None
        :param outpad: specify all the links with this outpad pad, defaults to None

        Only one of ``label``, ``inpad``, ``outpad`` should be specified. If
        more than one input argument is given, the preference is given in the
        order listed.

        If the specified link item does not exist, this function exits quietly.

        """
        if label is not None:
            if label in self.data:
                del self.data[label]
                # if int label removed, refresh auto-labels
                if isinstance(label, int):
                    self._refresh_autolabels()
        elif inpad is not None:
            label = self.find_inpad_label(inpad)
            if label is None:
                return
            if self.is_input_stream(label):
                # if input stream with multiple connections, only unlink the requested
                inpads, outpad = self.data[label]
                if len(inpads) == 1:
                    del self.data[label]
                else:
                    self.data[label] = (
                        tuple(pad for pad in inpads if pad != inpad),
                        outpad,
                    )
            else:
                del self.data[label]
        elif outpad is not None:
            label = self.find_outpad_label(outpad)
            if label is None:
                return
            del self.data[label]

    def rename(self, old_label: str, new_label: str, force: bool = False) -> str:
        """rename a label

        :param old_label: existing label (named or unnamed)
        :param new_label: new label name (possibly appended with a number if the label already exists)
        :param force: True to overwrite existing link by the same name as the `new_label`
        :return: renamed label name
        """

        if old_label not in self:
            raise ValueError(f"{old_label=} does not exist.")

        label_ = self.validate_label(new_label, is_link=self.is_linked(old_label))

        if label_ in self:
            if force:
                del self.data[label_]
            else:
                raise ValueError(f"{new_label} is already used.")

        v = self.data[old_label]
        del self.data[old_label]
        self.data[label_] = v
        return label_

    def remove_label(self, label: str, inpad: PAD_INDEX | None = None):
        """remove an input/output label

        :param label: unconnected link label
        :param inpad: (multi-input label only) specify the input filter pad id

        Removing an input label by default removes all associated filter pad ids
        unless `inpad` is specified.

        """

        if isinstance(label, int):
            raise ValueError(
                f"{label=} must be str. Use `unlink` to remove auto-numbered links."
            )

        try:
            inpads, outpad = self.data[label]
        except KeyError:
            raise GraphLinks.Error(f"{label} is not a valid link label.")

        if isinstance(inpads, tuple) and inpad is not None:  # input streams
            if inpad not in inpads:
                raise GraphLinks.Error(f"input pad {(inpad)} is not found")

            if len(inpads) > 1:
                # no other input pad indices assigne to the input stream
                del self.data[label]
            else:
                # remove only the requested input pad index
                self.data[label] = (
                    tuple(pad for pad in inpads if pad != inpad),
                    outpad,
                )
        else:
            # simple in/out label
            del self.data[label]

    def update(
        self,
        other: GraphLinks | dict[str | int, PAD_PAIR],
        auto_link: bool = False,
        force: bool = False,
        validate: bool = True,
    ):
        """Update the links with the label/id-pair pairs from other, overwriting existing keys. Return None.

        :param other: other object to copy existing items from
        :param auto_link: `True` to connect matching input-output labels, defaults to False
        :param preserve_label: `False` to remove the labels of the input and output pads (default) or
                               `'input'` to prefer the input label or `'output'` to prefer the output
                               label.
        :param force: True to overwrite existing link inpad id, defaults to False
        :param validate: False to skip the validation of the new links if not given as another `GraphLinks`,
                         defaults to True
        :returns: dict of given key to the actual labels assigned
        """

        if not isinstance(other, GraphLinks) and validate:
            try:
                assert isinstance(other, Mapping)
            except Exception:
                raise GraphLinks.Error("Other must be a dict-like mapping object")

            other = self.validate(other)

        # set aside labels
        labels = {
            l: is_input
            for l, (i, o) in other.items()
            if ((is_input := o is None) or i is None)
        }

        # create a working copy
        fglinks = GraphLinks()
        fglinks.data = self.data.copy()

        # add all the links
        for l, (i, o) in other.items():
            if l not in labels:
                fglinks.link(i, o, l, force=force)

        # add all the labels
        for l, is_input in labels.items():
            i, o = other[l]
            add_label = not auto_link
            if auto_link:
                if is_input and self.is_output(l):
                    fglinks.link(i, fglinks[l][1], preserve_label="output")
                elif not is_input and self.is_input(l):
                    fglinks.link(fglinks[l][0], o, preserve_label="input")
                else:
                    add_label = True
            if add_label:
                fglinks.create_label(l, i, o, force)

        # finalize
        self.data = fglinks.data

    def _is_inpad_used(self, pad: PAD_INDEX_) -> bool | str:
        """check if given input pad index is already linked

        :param pad: output pad index to check
        :return: ``True`` if ``pad`` is already connected to an input pad, or
            the output label ``str`` if the pad has a label but not connected
            yet, or ``False`` if no record is found.
        """

        for label, (inpads, outpad) in self.items():
            for inpad in self.iter_inpad_ids(inpads):
                if pad == inpad:
                    return label if outpad is None else True
        return False

    def _is_outpad_used(self, pad: PAD_INDEX_) -> bool | str:
        """check if given output pad index is already linked

        :param pad: output pad index to check
        :return: ``True`` if ``pad`` is already connected to an input pad, or
            the output label ``str`` if the pad has a label but not connected
            yet, or ``False`` if no record is found.
        """
        for label, (inpad, outpad) in self.items():
            if pad == outpad:
                return label if inpad is None else True
        return False

    def _refresh_autolabels(self):

        new_id = old_id = 0
        for new_id, old_id in enumerate(
            i for i, label in enumerate(self) if isinstance(label, int)
        ):
            self.data[new_id] = self.data[old_id]

        for id in range(new_id + 1, old_id + 1):
            del self.data[id]

    ############################################################################
    ### LINK manipulation
    ############################################################################

    @staticmethod
    def combine(
        link_objs: Sequence[GraphLinks | None], cumsum_chains: Sequence[int]
    ) -> tuple[GraphLinks, list[dict[tuple[int, str | int], str | int]] | None]:
        """combine ``GraphLinks`` objects into one, resolving duplicate labels

        :params link_objs: ``GraphLinks`` objects to be combined. If ``None``,
            the entry is ignored.
        :param cumsum_chains: cumulative sum of the number of chains of the
            filtergraphs that are associated with ``link_objs``
        :return combined_link_obj: a new ``GraphLinks`` object of all the links
            combined. Input streams are not linked, and they are returned
            separately as the third output below.
        :return mapping: list of mapping pairs for each element of
            ``link_objs``. Each mapping links ``link_objs`` item's old labels to
            its new labels in ``combined_link_obj``. If a ``link_objs`` element
            is a ``None``, a ``None`` is returned in ``mapping`` instead of a
            ``dict``.
        """

        # accumulate all the labels (remove trailing numbers if exist to match)
        labels: dict[str | int, list[tuple[int, str]]] = defaultdict(list)
        input_streams: dict[str, list[int]] = defaultdict(list)
        regexp = re.compile(r"\d+$")
        for i, (obj, cid0) in enumerate(zip(link_objs, cumsum_chains)):
            if obj is None:
                continue
            links = cast(GraphLinks, obj)
            for label in links:
                key = label
                if isinstance(key, str):
                    if links.is_input_stream(label):
                        # update the connected input pads
                        input_streams[label].extend(
                            [
                                (cid + cid0, fid, pid)
                                for cid, fid, pid in links[label][0]
                            ]
                        )
                        continue
                    else:
                        m = regexp.search(key)
                        if m:
                            key = key[: m.start()]

                labels[key].append((i, label))

        # create mapping table
        # - generate new labels for duplicated labels
        mappings = [obj and {} for obj in link_objs]
        int_counter = 0
        for key, matches in labels.items():
            if isinstance(key, int):
                # auto-labels (auto-label over all internal links)
                for i, old_label in matches:
                    new_label = int_counter
                    int_counter += 1
                    mappings[i][old_label] = new_label
            else:
                # explicit labels (append a unique suffix number)
                if len(matches) == 1:  # no duplicate, use as is
                    i, old_label = matches[0]
                    mappings[i][old_label] = key
                else:  # duplicates, append auto-#
                    for j, (i, old_label) in enumerate(matches):
                        new_label = f"{key}{j}"
                        mappings[i][old_label] = new_label

        # create the combined object
        combined = GraphLinks()
        for obj, cid0, mapping in zip(link_objs, cumsum_chains, mappings):
            if obj is None:
                continue
            links = cast(GraphLinks, obj)
            for label, (in_pad, out_pad) in links.items():
                if label not in mapping:
                    continue
                if in_pad is not None:
                    in_pad = (in_pad[0] + cid0, *in_pad[1:])
                if out_pad is not None:
                    out_pad = (out_pad[0] + cid0, *out_pad[1:])
                combined[mapping[label]] = (in_pad, out_pad)

        # add the input streams with the updated pad indices
        for label, in_pads in input_streams.items():
            combined.create_label(label, in_pads)

        return combined, mappings

    @staticmethod
    def pair_unconnected_labels(
        link_objs: Sequence[GraphLinks | None],
    ) -> list[tuple[str, int, int]]:
        """pair matched input and output labels and gather matched input streams

        :params link_objs: ``GraphLinks`` objects to be combined. If ``None``,
            the entry is ignored.
        :return combined_link_obj: a new ``GraphLinks`` object of all links
            combined
        :return: a list of tuples ``(label, in_index, out_index)`` of the pairs.
            ``in_index`` and ``out_index`` are indices to ``link_objs``.

        Note
        ----

        A pairing is only returned if and only if one-to-one match is found. If
        a label is used in 3 or more inputs or 3 or more outputs, those ports
        will not be reported as pairs.

        """

        # accumulate all the labels (remove trailing numbers if exist to match)
        input_labels = defaultdict(list)
        output_labels = defaultdict(list)
        for i, obj in enumerate(link_objs):
            if obj is None:
                continue
            links = cast(GraphLinks, obj)

            for label in links:
                if isinstance(label, int):
                    continue
                if links.is_input(label, exclude_stream_specs=True):
                    input_labels[label].append(i)
                elif links.is_output(label):
                    output_labels[label].append(i)

        # remove duplicate labels
        input_labels = {k: v[0] for k, v in input_labels.items() if len(v) == 1}
        output_labels = {k: v[0] for k, v in output_labels.items() if len(v) == 1}

        # return the matched input & output
        return [
            (label, in_obj, output_labels[label])
            for label, in_obj in input_labels.items()
            if label in output_labels
        ]

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

    def map_chains(
        self,
        mapper: int | Mapping[int, int] | None,
        shifter: Mapping[int, int] | None = None,
    ) -> GraphLinks:
        """Generate a new GraphLink object with a chain id mapper

        :param mapper: the current chain id as a key and the new chain id as its
        value. If an int value, all the chains are offset by the value.
        :param shifter: keyed chain links are shifted by the given value if specified

        Note: if a chain is indexed in both `mapper` and `shifter`, its links
        are first shifted then mapped.


        """

        if shifter is not None and len(shifter):

            def shift_padidx(pad):
                if pad[0] in shifter:
                    pad = (pad[0], pad[1] + shifter[pad[0]], pad[2])
                return pad

            def shift_pair(inpads, outpad):
                if outpad is not None:
                    outpad = shift_padidx(outpad)
                if inpads is not None:
                    if isinstance(inpads[0], int):  # single-input
                        inpads = shift_padidx(inpads)
                    else:  # multiple-inputs (an input stream)
                        inpads = tuple(shift_padidx(d) for d in inpads)
                return (inpads, outpad)

            data = {label: shift_pair(*value) for label, value in self.items()}
        else:
            data = self.data

        # check for duplicate value
        if isinstance(mapper, int):

            class OffsetMapper:
                nmap = len(self)

                def __init__(self, offset):
                    self._off = offset

                def __len__(self):
                    return self.nmap

                def __contains__(self, _):
                    # applies to all
                    return True

                def __getitem__(self, i):
                    return i + self._off

                def get(self, k, defaults=None):
                    return k + self._off

            mapper = OffsetMapper(mapper)

        if mapper is not None and len(mapper):

            def map_padidx(pad):
                if pad[0] in mapper:
                    pad = (mapper[pad[0]], *pad[1:])
                return pad

            def adjust_pair(inpads, outpad):
                if outpad is not None:
                    outpad = map_padidx(outpad)
                if inpads is not None:
                    if isinstance(inpads[0], int):  # single-input
                        inpads = map_padidx(inpads)
                    else:  # multiple-inputs (an input stream)
                        inpads = tuple(map_padidx(d) for d in inpads)
                return (inpads, outpad)

            data = {label: adjust_pair(*value) for label, value in data.items()}

        fglinks = GraphLinks()
        fglinks.data = data
        return fglinks

    def combine_chains(self, out_pad: PAD_INDEX, in_pad: PAD_INDEX, n_out: int):
        """adjust pad indices as two chains are combined

        :param cid_out: id of the host chain
        :param cid_in: id of the moving chain
        :param n_out: number of filters of the host chain

        .. warning::
           this operation does not check for the existence of a link between the
           last output pad of the last filter of the ``cid_out`` chain and the
           last input pad of the first filter of the ``cid_in`` chain. The
           caller must remove such link if it exists.

        """

        # check that the pads to be chained are available
        # (no go if either pads are already connected)
        label_out = self.find_outpad_label(out_pad)
        label_in = self.find_inpad_label(in_pad)
        if label_in == label_out:
            if label_in is not None:
                self.remove_label(label_in)
        else:
            if label_out is not None:
                if self.is_linked(label_out):
                    raise ValueError(
                        f"cannot combine chains because {out_pad=} is already linked"
                    )
                self.remove_label(label_out)

            if label_in is not None:  # in_pad already used
                if self.is_linked(label_in) and not self.are_linked(in_pad, out_pad):
                    raise ValueError(
                        f"cannot combine chains because {in_pad=} is already linked"
                    )
                self.remove_label(label_in)

            cid_out, cid_in = out_pad[0], in_pad[0]

        # update all the pad indices appearing after the input chain
        for label, (inpad, outpad) in self.items():
            cid_out, cid_in = out_pad[0], in_pad[0]

            if isinstance(inpad, tuple):
                if isinstance(inpad[0], int):
                    # input label
                    if inpad[0] == cid_in:
                        inpad = (cid_out, inpad[1] + n_out, inpad[2])
                    elif inpad[0] > cid_in:
                        inpad = (inpad[0] - 1, *inpad[1:])
                else:
                    # pads connected to an input stream are always in a nested tuple
                    inpad = [
                        (cid_out, pad[1] + n_out, pad[2])
                        if pad[0] == cid_in
                        else (pad[0] - 1, *pad[1:])
                        if pad[0] > cid_in
                        else pad
                        for pad in inpad
                    ]

            if outpad is not None:
                if outpad[0] == cid_in:
                    outpad = (cid_out, outpad[1] + n_out, outpad[2])
                elif outpad[0] > cid_in:
                    outpad = (outpad[0] - 1, *outpad[1:])
            self[label] = (inpad, outpad)

    def adjust_chains(self, pos: int, len: int):
        """insert/delete contiguous chains from fg

        :param pos: position of the first chain
        :param len: number of chains to be inserted (if positive) or removed (if negative)
        """

        select = lambda pid: pid[0] >= pos  # select all chains at or above pos
        adjust = lambda pid: (pid[0] + len, *pid[1:])
        self._modify_pad_ids(select, adjust)

    def adjust_filters(self, chain_id: int, pos: int, len: int):
        """insert/delete contiguous filters from specified filter chain

        :param chain_id: id of the filter chain to be adjusted
        :param pos: position of the first chain
        :param len: number of chains to be inserted (if positive) or removed (if negative)
        """

        select = lambda pid: (
            pid[0] == chain_id and pid[1] >= pos
        )  # select all chains at or above pos
        adjust = lambda pid: (pid[0], pid[1] + len, pid[2])
        self._modify_pad_ids(select, adjust)

    ############################################################################

    def is_linked(self, label: str, include_stream_specs: bool = False) -> bool:
        """True if label specifies a link

        :param label: link label
        :return: True if label is a link

        If multi-inpad label, True if any inpad is not None
        """
        inpad, outpad = self.data.get(label, (None, None))
        is_link = inpad is not None and outpad is not None
        if not is_link and include_stream_specs:
            is_link = self.is_input_stream(label)
        return is_link

    def is_input(self, label: str, exclude_stream_specs: bool = False) -> bool:
        """True if label specifies an input

        :param label: link label
        :param exclude_stream_specs: ``True`` to return ``False`` if the label
            is an input stream spec.
        :return: ``True`` if label is an input
        """
        lnk = self.data.get(label, None)
        return (
            lnk
            and lnk[0] is not None
            and lnk[1] is None
            and not (exclude_stream_specs and isinstance(lnk[0][0], tuple))
        )

    def is_input_stream(self, label: str) -> bool:
        """``True`` if label specifies an input stream map

        :param label: input stream map specifier
        :return: ``True`` if label is an input
        """

        lnk = self.data.get(label, None)
        return (
            lnk is not None
            and lnk[0] is not None
            and lnk[1] is None
            and isinstance(lnk[0][0], tuple)
        )

    def is_output(self, label: str) -> bool:
        """``True`` if label specifies an output

        :param label: link label
        :return: ``True`` if label is an output

        If multi-inpad label, True if any inpad is None
        """
        lnk = self.data.get(label, None)
        return lnk and lnk[0] is None

    def iter_input_pads(
        self, label: str | None = None
    ) -> Generator[str, PAD_INDEX_, PAD_INDEX_ | None]:
        """Iterate over all link elements, possibly separating inpad ids with
           the same label

        :param label: to iterate only on this label, defaults to None (all frames)
        :yield: a full link definition (inpad or outpad may be None if input or output label, respectively)
        """

        def iter(label, inpad, outpad):
            for d in self.iter_inpad_ids(inpad, True):
                yield (label, d, outpad)

        if label is None:
            # all input pads
            for label, (inpad, outpad) in self.data.items():
                for v in iter(label, inpad, outpad):
                    yield v
        else:
            # only specified label
            for v in iter(label, *self.data[label]):
                yield v

    def iter_output_pads(
        self, label: str | None = None
    ) -> Generator[str, PAD_INDEX_, PAD_INDEX_ | None]:
        """Iterate over all ``GraphLinks`` items with an assigned output pad

        :param label: to iterate only on this label, defaults to None (all frames)
        :yield label: a full link definition (inpad or outpad may be None if input or output label, respectively)
        :yield inpad: input pad index
        :yield outpad: output pad index
        """

        if label is None:  # all output pads
            for label, (inpad, outpad) in self.data.items():
                if outpad is not None:
                    yield (label, inpad, outpad)
        else:
            yield label, *self.data[label]

    def iter_links(
        self, label: str | None = None, include_input_stream: bool = False
    ) -> Generator[tuple[str, PAD_INDEX_, PAD_INDEX_ | None]]:
        """Iterate over only actual links, separating inpad ids with
           the same input stream

        :param label: to iterate only on this label, defaults to None (all frames)
        :param include_input_stream: True to include input pads connected to input streams.
        :yield: label, input pad, and output pad of a link
        """

        def iter(label, inpad, outpad):
            if outpad is not None and (
                inpad is not None or (include_input_stream and isinstance(inpad, tuple))
            ):
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
    ) -> Generator[tuple[str, PAD_INDEX_]]:
        """Iterate over only input labels, possibly repeating the same label if shared among
           multiple input pad ids

        :param exclude_stream_specs: True to not include input streams
        :param only_stream_specs: True to only include input streams
        :yield: label and pad index
        """
        for label, (inpad, outpad) in self.data.items():
            if outpad is None and not (
                exclude_stream_specs and isinstance(inpad, tuple)
            ):
                for d in self.iter_inpad_ids(inpad):
                    yield (label, d)

    def iter_input_streams(self) -> Generator[tuple[str, PAD_INDEX_]]:
        """Iterate over input stream labels, possibly repeating the same label if shared among
           multiple input pad ids

        :yield: label and pad index
        """
        for label, (inpad, _) in self.data.items():
            if isinstance(inpad, tuple):
                for d in self.iter_inpad_ids(inpad):
                    yield (label, d)

    def iter_outputs(self) -> Generator[tuple[str, PAD_INDEX_]]:
        """Iterate over only output labels

        :yield: output label and pad index
        """

        # iterate over all labels
        for label, (inpad, outpad) in self.data.items():
            if inpad is None:
                yield (label, outpad)

    def input_dict(self) -> dict[PAD_INDEX_, PAD_INDEX_ | str]:
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

    def output_dict(self) -> dict[PAD_INDEX_, PAD_INDEX_ | str]:
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

    def find_inpad_label(self, inpad: PAD_INDEX) -> str | int | None:
        """get label of an input pad id

        :param inpad: input filter pad id
        :return: found label or None if no match found
        """
        try:
            return next(
                (
                    label
                    for label, dst1, _ in self.iter_input_pads()
                    if dst1 is not None and inpad == dst1
                ),
                None,
            )
        except StopIteration:
            return None

    def find_outpad_label(self, outpad: PAD_INDEX) -> str | int | None:
        """get labels of a source/output pad id

        :param inpad: output filter pad id
        :return: found label or None if outpad is None
        """
        try:
            return next(
                label
                for label, (_, src1) in self.data.items()
                if src1 is not None and outpad == src1
            )
        except StopIteration:
            return None

    def are_linked(
        self,
        inpad: PAD_INDEX | None,
        outpad: PAD_INDEX | None,
        check_input_stream: bool | None = None,
    ) -> bool:
        """True if given pads are linked

        :param inpad: input pad index, default to ``None`` to check if
            ``outpad`` is connected to any input pad.
        :param outpad: output pad index, defaults to ``None`` to check if
            ``inpad`` is connected to any output pad or an input stream.
        :param check_input_stream: ``True`` to check inpad is connected to an
            input stream, or the default (``None``) behavior to return ``False``
            for an ambiguous label such as ``'a'`` or ``'v'``, and ``True`` for
            definitive label such as ``'0:v:0'``.

        ``ValueError`` will be raised if both ``inpad`` and ``outpad`` ``None`` or
        if ``include_input_stream!=False`` and ``outpad`` is ``None``.

        """

        if inpad is None and outpad is None:
            raise ValueError("At least one of inpad or outpad must be specified.")

        inpad = self.validate_pad_idx(inpad, none_ok=True)
        outpad = self.validate_pad_idx(outpad, none_ok=True)

        if inpad is None:  # any link with outpad
            return any(inp is not None for _, inp, __ in self.iter_output_pads())
        elif outpad is None:  # any link with inpad
            for label, inp, outp in self.iter_input_pads():
                if inp is None:
                    continue

                if inp == inpad and outp is not None:
                    return True

                # check input stream link
                if check_input_stream is not False and isinstance(inp[0], tuple):
                    if check_input_stream is True and any(p == inpad for p in inp[0]):
                        return True

                    if check_input_stream is None and len(inp) == 1 and inp[0] == inpad:
                        # ambiguous input stream connection if it is also a valid link label
                        return re.match(r"[a-zA-Z0-9_]+$", label) is not None
        else:  # specific pairing
            return any(
                inp == inpad and outp == outpad for _, inp, outp in self.iter_links()
            )
        return False

    def chain_has_link(
        self, chain_id: int, check_input: bool = True, check_output: bool = True
    ) -> bool:
        """True if there is any link/label defined on the chain specified by its id

        :param chain_id: index of the chain under test
        :param check_input: True to check all the input pads, defaults to True
        :param check_output: _description_, defaults to True
        """
        for inpads, outpad in self.values():
            if check_output and outpad and outpad[0] == chain_id:
                return True
            if check_input and any(
                inpad[0] == chain_id for inpad in self.iter_inpad_ids(inpads)
            ):
                return True
        return False

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
