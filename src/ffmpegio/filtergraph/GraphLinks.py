from __future__ import annotations

import re
from collections import UserDict, defaultdict
from collections.abc import Callable, Generator, Mapping, Sequence
from copy import deepcopy

from ..errors import FFmpegioError
from ..stream_spec import is_map_option
from .typing import PAD_INDEX, PAD_PAIR, Literal, cast

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
    def validate_label(
        label: str | int, is_link: bool = False, no_stream_spec: bool = False
    ):
        if isinstance(label, int):
            if not is_link:
                raise GraphLinks.Error(
                    "A pad label without a link must be a string label."
                )
        else:
            if not (isinstance(label, str) and len(label)):
                raise GraphLinks.Error(
                    "Pad label must be a string and has at least one character."
                )
            if no_stream_spec and is_map_option(label, allow_missing_file_id=True):
                raise GraphLinks.Error(
                    f"Pad label cannot be an input stream specifier ({label})."
                )

    @staticmethod
    def validate_pad_idx(id: PAD_INDEX | None, none_ok: bool = True):

        if id is None:
            if none_ok:
                return
            raise GraphLinks.Error("pad index cannot be None")

        if not (
            isinstance(id, (tuple))
            and len(id) == 3
            and all((isinstance(i, int) and i >= 0 for i in id))
        ):
            raise GraphLinks.Error(
                f"{id=} is not a valid filter pad ID. Filter pad ID must be a 3-element tuple: (chain id, filter id, pad id)"
            )

    @staticmethod
    def validate_pad_idx_pair(ids: PAD_PAIR):

        try:
            assert len(ids) == 2
        except:
            raise GraphLinks.Error(
                "Link value must be a 2-element tuple with inpad and outpad pad ids"
            )

        (inpad, outpad) = ids
        GraphLinks.validate_pad_idx(outpad)

        inpad_is_none = inpad is None
        if inpad_is_none and outpad is None:
            raise GraphLinks.Error("Both input and output pads cannot be None.")

        i = -1
        for i, d in enumerate(GraphLinks.iter_inpad_ids(inpad, True)):
            if d is None and not inpad_is_none:
                raise GraphLinks.Error("multi-id input label item cannot be None.")
            GraphLinks.validate_pad_idx(d)

    @staticmethod
    def validate_item(label: str | int, pads: PAD_PAIR):

        GraphLinks.validate_pad_idx_pair(pads)  # this fails if None-None pair

        inpad_given = pads[0] is not None
        outpad_given = pads[1] is not None

        GraphLinks.validate_label(
            label, is_link=inpad_given and outpad_given, no_stream_spec=outpad_given
        )

    @staticmethod
    def validate(data: dict[str | int, PAD_PAIR]):

        inpads = set()  # inpad cannot be repeated

        # validate each link
        for label, pads in data.items():
            if (
                not is_map_option(label, allow_missing_file_id=True)
                and pads[0] is not None
                and isinstance(pads[0][0], tuple)
            ):
                raise GraphLinks.Error(
                    "Only map specifier labels can have multiple input pads."
                )

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
    AutoLabelPattern = re.compile(r"^L\d+?$")

    def __init__(
        self,
        links: dict[str | int, PAD_PAIR] | GraphLinks | None = None,
    ):

        # calls update() if links set
        super().__init__()

        # validate input arg
        if isinstance(links, GraphLinks):
            self.data = links.data.copy()
        elif links is not None:
            links = {k: self.format_value(*v) for k, v in links.items()}
            self.update(links)

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
        :param label: desired label name, defaults to None (=reuse inpad/outpad label or unnamed link)
        :param preserve_label: `False` to remove the labels of the input and output pads (default) or
                               `'input'` to prefer the input label or `'output'` to prefer the output
                               label.
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

        self.validate_pad_idx(inpad, none_ok=False)
        self.validate_pad_idx(outpad, none_ok=False)

        # check if inpad already exists and resolve conflict if there is one
        in_label = self.find_inpad_label(inpad)
        if in_label is not None:
            if not (force or self.is_input(in_label)):
                raise GraphLinks.Error(f"input pad {inpad} already linked.")
            if (force and self.is_linked(in_label)) or preserve_label != "input":
                # if in_label has multi-inpads, cannot reuse it
                self.unlink(inpad=inpad)
                in_label = None

        # check if output label already exists. pick the first match
        out_label = self.find_outpad_label(outpad)
        if out_label is not None:
            if not force and self.is_linked(out_label):
                raise GraphLinks.Error(f"output pad {outpad} already linked.")
            if (force and self.is_linked(out_label)) or preserve_label != "output":
                # if in_label has multi-inpads, cannot reuse it
                self.unlink(outpad=outpad)
                out_label = None

        # finalize the label name
        # if not defined by user, select new label to be inpad or outpad label if found

        if label is None and preserve_label is not False:
            label = (
                out_label
                if preserve_label == "output" or in_label is None
                else in_label
            )

        if not (in_label or out_label):
            # new label, resolve
            label = self.resolve_label(label, force)

        # create the new link (overwrite if forced)
        self.data[label] = (inpad, outpad)

        return label

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
                label = self.resolve_label(None)
                linked = False
            else:
                raise ValueError(f"{preserve_label=} is not a valid value.")
        else:
            self.validate_label(label)

        if not linked:
            self[label] = link_value
            del self[in_label]
            del self[out_label]

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
            label = self.find_outpad_label(outpad)
            if label is not None:
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

        if isinstance(label, int):
            self._refresh_autolabels()

    def _refresh_autolabels(self):

        new_id = old_id = 0
        for new_id, old_id in enumerate(
            i for i, label in enumerate(self) if isinstance(label, int)
        ):
            self.data[new_id] = self.data[old_id]

        for id in range(new_id + 1, old_id + 1):
            del self.data[id]

    def resolve_label(
        self,
        label: str | int | None,
        force: bool = False,
        check_stream_spec: bool = True,
        auto_index: bool = False,
        auto_index_sep: str = "",
    ) -> str | int:
        """check the label name for duplicate, adjust as needed

        :param label: suggested new label name. If int or `"L<int>"` or `None`, the given label
                      is ignored and replaced with the autonumbering label
        :param force: True to allow overwrite an existing label, defaults to False
        :param check_stream_spec: False to skip stream spec check, defaults to True
        :param auto_index: True to append a number to a string label until a unique
                           label is found, defaults to False to error out.
        :param auto_index_sep: a string to separate the label and the auto-index number,
                               defaults to ''
        :return: validated label name/id
        """

        if isinstance(label, (type(None), int)) or self.AutoLabelPattern.match(label):
            try:
                return max(i for i in self if isinstance(i, int)) + 1
            except ValueError:
                return 0

        if check_stream_spec and is_map_option(label, allow_missing_file_id=True):
            return label

        if not force and label in self:
            if not auto_index:
                raise GraphLinks.Error(f"{label=} is already in use.")
            i = 0
            label_ = f"{label}{auto_index_sep}"
            while label in self:
                i += 1
                label = f"{label_}{i}"

        self.validate_label(label)

        return label

    @staticmethod
    def combine(
        link_objs: Sequence[GraphLinks | None], cumsum_chains: Sequence[int]
    ) -> tuple[GraphLinks, list[dict[tuple[int, str | int], str | int]]]:
        """combine ``GraphLinks`` objects into one, resolving duplicate labels

        :params link_objs: ``GraphLinks`` objects to be combined. If ``None``,
            the entry is ignored.
        :param cumsum_chains: cumulative sum of the number of chains of the
            filtergraphs that are associated with ``link_objs``
        :return combined_link_obj: a new ``GraphLinks`` object of all the links
            combined. Input streams are not linked, and they are returned
            separately as the third output below.
        :return mapping: mapping a pair of ``link_objs`` index and its old label
            to its new labels in ``combined_link_obj``.
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
                        input_streams[label].append(
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
                for j, (i, old_label) in enumerate(matches):
                    new_label = f"{key}{j}"
                    mappings[i][old_label] = new_label

        # create the combined object
        combined = GraphLinks()
        for obj, cid0 in zip(link_objs, cumsum_chains):
            if obj is None:
                continue
            links = cast(GraphLinks, obj)
            for label, (in_pad, out_pad) in links.items():
                in_pad = (in_pad[0] + cid0, *in_pad[1:])
                out_pad = (out_pad[0] + cid0, *out_pad[1:])
                combined[mappings[label]] = (in_pad, out_pad)

        # add the input streams with the updated pad indices
        for label, in_pads in input_streams.items():
            combined.create_label(label, in_pads)

        return combined, mappings

    def relabel(self) -> GraphLinks:
        """relabel ``GraphLinks``
        :return: a new ``GraphLinks`` object of all the internal int labels
            renumbered as well as the trailing numbers of user labels
        """

        # accumulate all the labels (remove trailing numbers if exist to match)
        labels: dict[str | int, list[str | int]] = defaultdict(list)
        regexp = re.compile(r"\d+$")

        for label in self:
            key = label
            if isinstance(key, str):
                m = regexp.search(key)
                if m:
                    key = key[: m.start()]

            labels[key].append(label)

        # create mapping table
        # - generate new labels for duplicated labels
        mappings = {}
        int_counter = 0
        for key, matches in labels.items():
            if isinstance(key, int):
                # auto-labels (auto-label over all internal links)
                for old_label in matches:
                    new_label = int_counter
                    int_counter += 1
                    mappings[old_label] = new_label
            else:
                # explicit labels (append a unique suffix number)
                for j, old_label in enumerate(matches):
                    new_label = f"{key}{j}"
                    mappings[old_label] = new_label

        # create the combined object
        new_links = GraphLinks()
        for label, link in self.items():
            new_links[mappings[label]] = deepcopy(link)

        return new_links

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

    def __getitem__(self, key: str | int) -> PAD_PAIR:
        """get link item by label or by inpad pad id tuple

        :param key: label name or inpad pad id tuple (int,int,int)
        :return: link inpads-outpad pair, if input pad is `None`, the key is an
                 output label or if output pad is `None`, the key is an input label
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

    def __setitem__(self, key: str | int, value: PAD_PAIR):
        # can only set named key
        if value[0] is None:
            self.create_label(key, outpad=value[1], force=True)
        elif value[1] is None:
            self.create_label(key, inpad=value[0], force=True)
        else:
            self.link(value[0], value[1], label=key, force=True)

    def is_linked(self, label: str) -> bool:
        """True if label specifies a link

        :param label: link label
        :return: True if label is a link

        If multi-inpad label, True if any inpad is not None
        """
        lnk = self.data.get(label, (None, None))
        return lnk[1] is not None and any(self.iter_inpad_ids(lnk[0]))

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
            and lnk[1] is None
            and (not exclude_stream_specs or isinstance(lnk[0], str))
        )

    def is_input_stream(self, label: str) -> bool:
        """``True`` if label specifies an input stream map

        :param label: input stream map specifier
        :param exclude_stream_specs: ``True`` to return ``False`` if the label
            is an input stream spec.
        :return: ``True`` if label is an input
        """
        lnk = self.data.get(label, None)
        return lnk and lnk[1] is None and not isinstance(lnk[0], str)

    def is_output(self, label: str) -> bool:
        """``True`` if label specifies an output

        :param label: link label
        :return: ``True`` if label is an output

        If multi-inpad label, True if any inpad is None
        """
        lnk = self.data.get(label, None)
        return lnk and any((d is None for d in self.iter_inpad_ids(lnk[0], True)))

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
            if outpad is not None or (
                include_input_stream
                and is_map_option(label, allow_missing_file_id=True)
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
        self, exclude_stream_specs: bool = True, only_stream_specs: bool = False
    ) -> Generator[tuple[str, PAD_INDEX]]:
        """Iterate over only input labels, possibly repeating the same label if shared among
           multiple input pad ids

        :param exclude_stream_specs: True to not include input streams
        :param only_stream_specs: True to only include input streams
        :yield: label and pad index
        """
        for label, (inpad, outpad) in self.data.items():
            is_stream = is_map_option(label, allow_missing_file_id=True)
            if outpad is None and (
                (is_stream and not exclude_stream_specs)
                or not (is_stream or only_stream_specs)
            ):
                for d in self.iter_inpad_ids(inpad):
                    yield (label, d)

    def iter_input_streams(self) -> Generator[tuple[str, PAD_INDEX]]:
        """Iterate over input stream labels, possibly repeating the same label if shared among
           multiple input pad ids

        :yield: label and pad index
        """
        for label, (inpad, outpad) in self.data.items():
            if outpad is None and is_map_option(label, allow_missing_file_id=True):
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
                raise ValueError("At least one of inpad or outpad must be specified.")

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

        if not isinstance(label, str):
            raise ValueError(f"{label=} must be a string.")

        if (outpad is None) == (inpad is None):
            raise ValueError("outpad or inpad (but not both) must be given.")

        is_stspec = is_map_option(label, allow_missing_file_id=True)
        if not is_stspec:
            label = self.resolve_label(label, force=force, check_stream_spec=False)

        label_in_use = label in self

        # check if inpad already exists and resolve conflict if there is one
        if outpad:
            if is_stspec:
                raise ValueError(
                    "stream specifier ({label}) cannot be specified as an output label."
                )

            pad_in_use = self.find_outpad_label(outpad)

            if label == pad_in_use:
                # already labeled as specified
                return label

        else:
            pad_in_use = self.find_inpad_label(inpad)

            if is_stspec:
                # multiple connections allowable (always use tuple to store even if 1)

                inpad0 = self.data.get(label, (None,))[0]
                # just in case
                if inpad0 is None:
                    inpad0 = ()
                elif isinstance(inpad0[0], int):
                    inpad0 = (inpad0,)
                inpad = (*inpad0, *(inpad if isinstance(inpad[0], tuple) else (inpad,)))
                label_in_use = False  # OK to overwrite
                if pad_in_use == label:
                    pad_in_use = None
            elif label == pad_in_use:
                return label

        if force:
            if pad_in_use:
                del self[pad_in_use]
        else:
            if label_in_use:
                raise GraphLinks.Error(f"{label=} is already in use")
            if pad_in_use:
                raise GraphLinks.Error(
                    f"{pad_in_use=} is already using the specified pad: {inpad or outpad}"
                )

        self.data[label] = (inpad, outpad)
        return label

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

    def rename(self, old_label: str, new_label: str, force: bool = False) -> str:
        """rename a label

        :param old_label: existing label (named or unnamed)
        :param new_label: new label name (possibly appended with a number if the label already exists)
        :param force: True to overwrite existing link by the same name as the `new_label`
        :return: renamed label name
        """
        v = self.data[old_label]
        label = self.resolve_label(new_label, force)
        del self.data[old_label]
        self.data[label] = v
        return label

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
            self.validate(other)

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

    def combine_chains(self, cid_out: int, cid_in: int, n_out: int):
        for label, (inpad, outpad) in self.items():
            if isinstance(inpad, tuple):
                if inpad[0] == cid_in:
                    inpad = (cid_out, inpad[1] + n_out, inpad[2])
                elif inpad[0] > cid_in:
                    inpad = (inpad[0] - 1, *inpad[1:])
            elif isinstance(inpad, list):
                inpad = [
                    (cid_out, pad[1] + n_out, pad[2])
                    if pad[0] == cid_in
                    else (pad[0] - 1, *pad[1:])
                    if pad[0] > cid_in
                    else pad
                    for pad in inpad
                ]
            if outpad[0] == cid_in:
                outpad = (cid_out, outpad[1] + n_out, outpad[2])
            elif outpad[0] > cid_in:
                outpad = (outpad[0] - 1, *outpad[1:])
            self[label] = (inpad, outpad)
