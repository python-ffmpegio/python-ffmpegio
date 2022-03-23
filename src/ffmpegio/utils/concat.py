"""ConcatDemuxer class to 
"""

import io, re
from tempfile import NamedTemporaryFile
from functools import partial

from . import escape, unescape

# https://trac.ffmpeg.org/wiki/Concatenate
# https://ffmpeg.org/ffmpeg-formats.html#concat

# options
# -safe
#    If set to 1, reject unsafe file paths and directives. A file path is considered safe if it does not contain a protocol specification and is relative and all components only contain characters from the portable character set (letters, digits, period, underscore and hyphen) and have no period at the beginning of a component.
#    If set to 0, any file name is accepted.
#    The default is 1.
# -auto_convert
#    If set to 1, try to perform automatic conversions on packet data to make the streams concatenable. The default is 1.
#    Currently, the only conversion is adding the h264_mp4toannexb bitstream filter to H.264 streams in MP4 format. This is necessary in particular if there are resolution changes.
# -segment_time_metadata
#    If set to 1, every packet will contain the lavf.concat.start_time and the lavf.concat.duration packet metadata values which are the start_time and the duration of the respective file segments in the concatenated output expressed in microseconds. The duration metadata is only set if it is known based on the concat file. The default is 0.

# list entries
# file path
#     Path to a file to read; special characters and spaces must be escaped with backslash or single quotes.
#     All subsequent file-related directives apply to that file.
# duration dur
#     * Duration of the file. This information can be specified from the file; specifying it here may be more efficient or
#       help if the information from the file is not available or accurate.
#     * If the duration is set for all files, then it is possible to seek in the whole concatenated video.
# inpoint timestamp
#     * In point of the file. When the demuxer opens the file it instantly seeks to the specified timestamp. Seeking is done
#       so that all streams can be presented successfully at In point.
#     * This directive works best with intra frame codecs, because for non-intra frame ones you will usually get extra
#       packets before the actual In point and the decoded content will most likely contain frames before In point too.
#     * For each file, packets before the file In point will have timestamps less than the calculated start timestamp of
#       the file (negative in case of the first file), and the duration of the files (if not specified by the duration
#       directive) will be reduced based on their specified In point.
#     * Because of potential packets before the specified In point, packet timestamps may overlap between two concatenated
#       files.
# outpoint timestamp
#     * Out point of the file. When the demuxer reaches the specified decoding timestamp in any of the streams, it handles it
#       as an end of file condition and skips the current and all the remaining packets from all streams.
#     * Out point is exclusive, which means that the demuxer will not output packets with a decoding timestamp greater or
#       equal to Out point.
#     * This directive works best with intra frame codecs and formats where all streams are tightly interleaved. For non-intra
#       frame codecs you will usually get additional packets with presentation timestamp after Out point therefore the decoded
#       content will most likely contain frames after Out point too. If your streams are not tightly interleaved you may not
#       get all the packets from all streams before Out point and you may only will be able to decode the earliest stream
#       until Out point.
#     * The duration of the files (if not specified by the duration directive) will be reduced based on their specified Out
#       point.
# file_packet_meta key value
#     * Metadata of the packets of the file. The specified metadata will be set for each file packet. You can specify this
#       directive multiple times to add multiple metadata entries.


# stream
#     * Introduce a stream in the virtual file. All subsequent stream-related directives apply to the last introduced stream.
#       Some streams properties must be set in order to allow identifying the matching streams in the subfiles. If no streams
#       are defined in the script, the streams from the first file are copied.
# exact_stream_id id
#     * Set the id of the stream. If this directive is given, the string with the corresponding id in the subfiles will be
#       used. This is especially useful for MPEG-PS (VOB) files, where the order of the streams is not reliable.
# stream_meta key value
#     * Metadata for the stream. Can be present multiple times.
# stream_codec value
#     * Codec for the stream.
# stream_extradata hex_string
#     * Extradata for the string, encoded in hexadecimal.


# option key value
#     Option to access, open and probe the file. Can be present multiple times.


class ConcatDemuxer:
    """Create FFmpeg concat demuxer source generator

    :param script: concat script to parse, defaults to None (empty script)
    :type script: str, optional
    :param pipe_url: stdin pipe or None to use a temp file, defaults to None
    :type pipe_url: bool, optional

    ConcatDemuxer instance is intended to be used as an input url object when invoking `ffmpegprocess.run`
    or `ffmpegprocess.Popen`. The FFmpeg command parser stringify the ConatDemuxer instance to either the
    temp file path or the pipe name, depending on the chosen operation mode. The temporary listing is
    automatically generated within the ConcatDemuxer context. If the listing is send in via pipe, the
    listing data can be obtained via `concat_demuxer.input`.

    The listing can be populated either by parsing a valid ffconcat script via the constructor or
    `concat_demuxer.parse()`. Or an individual item (file, stream, option, or chapter) can be added by
    `concat_demuxer.add_file()`, `concat_demuxer.add_stream()`, `concat_demuxer.add_option()`, or
    `concat_demuxer.add_chapter()`. Files can also be added in batch by `concat_demuxer.add_files()`.

    Aside from the intended operations with `ffmpegprocess`, a listing file can be explicitly created by
    calling `concat_demuxer.compose()` with a valid writable text file object.

    Examples
    --------

    1. Concatenate mp4 files with listing piped to stdin

    ```python

    files = ['video1.mp4','video2.mp4']
    concat_demuxer = ffmpegio.ConcatDemuxer(pipe_url='-')
    concat_demuxer.add_files(files)
    ffmpegio.transcode(concat_demuxer,'output.mp4')
    ```

    2. Concatenate mp4 files with a temp listing file

    ```python

    files = ['video1.mp4','video2.mp4']
    concat_demuxer = ffmpegio.ConcatDemuxer()
    concat_demuxer.add_files(files)
    with concat_demuxer:
        ffmpegio.transcode(concat_demuxer,'output.mp4')

    ```

    The concat script may be populated/altered inside the `with` statement, 
    but `refresh()` must be called to update the script:

    ```python

    files = ['video1.mp4','video2.mp4']
    with ffmpegio.ConcatDemuxer() as concat_demuxer:
        concat_demuxer.add_files(files)
        concat_demuxer.refresh()
        ffmpegio.transcode(concat_demuxer,'output.mp4')

    ```

    """

    class FileItem:
        """Create a file listing item

        :param filepath: url of the file to be included
        :type filepath: str
        :param duration: duration of the file, defaults to None
        :type duration: str or numeric, optional
        :param inpoint: in point of the file, defaults to None
        :type inpoint: str or numeric, optional
        :param outpoint: out point of the file, defaults to None
        :type outpoint: str or numeric, optional
        :param metadata: Metadata of the packets of the file, defaults to None
        :type metadata: dict, optional
        """

        def __init__(
            self, filepath, duration=None, inpoint=None, outpoint=None, metadata=None
        ):
            self.path = filepath
            self.duration = duration
            self.inpoint = inpoint
            self.outpoint = outpoint
            self.metadata = metadata or {}

        @property
        def lines(self):
            if not self.path:
                raise RuntimeError("Invalid FileItem. File path must be set.")
            lines = [
                f"file {escape(self.path)}\n",
                *(
                    f"{k} {getattr(self,k)}\n"
                    for k in ("duration", "inpoint", "outpoint")
                    if getattr(self, k) is not None
                ),
            ]
            if self.metadata is not None:
                lines.extend(
                    [
                        f"file_packet_meta {k} {escape(v)}\n"
                        for k, v in self.metadata.items()
                    ]
                )
            return lines

    class StreamItem:
        """Create a stream listing item

        :param id: ID of the stream, defaults to None
        :type id: str, optional
        :param codec: Codec for the stream, defaults to None
        :type codec: str, optional
        :param metadata: Metadata for the stream, defaults to None
        :type metadata: dict, optional
        :param extradata: Extradata for the stream in hexadecimal, defaults to None
        :type extradata: str or bytes-like, optional
        """

        def __init__(self, id=None, codec=None, metadata=None, extradata=None):
            self.id = id
            self.codec = codec
            self.metadata = metadata or {}
            self.extradata = extradata

        @property
        def lines(self):

            if all(
                (getattr(self, k) is None for k in ("id", "codec", "extradata"))
            ) and not len(self.metadata):
                raise RuntimeError(
                    "Invalid StreamItem. At least one attribute must be set."
                )

            lines = ["stream\n"]
            if self.id is not None:
                lines.append(f"exact_stream_id {self.id}\n")
            if self.codec is not None:
                lines.append(f"stream_codec {self.codec}\n")
            if self.metadata is not None:
                lines.extend(
                    [f"stream_meta {k} {escape(v)}\n" for k, v in self.metadata.items()]
                )
            if self.extradata is not None:
                lines.append(
                    f"stream_extradata {self.extradata if isinstance(self.extradata,str) else memoryview(self.extradata).hex()}\n"
                )

            return lines

    def __init__(self, script=None, pipe_url=None):
        self.files = (
            []
        )  # :List[ConcatDemuxer.FileItem]: list of files to be included in the order of appearance
        self.streams = (
            []
        )  #:ListConcatDemuxer.StreamItem]: list of streams to be included in the order of appearance
        self.options = {}  #:dict[str,Any]: option key-value pairs to be included
        self.chapters = (
            {}
        )  #:dict[str,tuple]: chapter id-(start,end) pairs to be included
        self.pipe_url = pipe_url  #:str|None: specify pipe url if concat script to be loaded via stdin; None via a temp file
        self._temp_file = None  # used by context manager

        if script is not None:
            self.parse(script)

    @property
    def last_file(self):
        """:ConcatDemuxer.FileItem: Last added file item"""
        try:
            return self.files[-1]
        except:
            raise ValueError("No file defined.")

    @property
    def last_stream(self):
        """:ConcatDemuxer.StreamItem: Last added stream item"""
        try:
            return self.streams[-1]
        except:
            raise ValueError("No stream defined.")

    def add_file(
        self, filepath, duration=None, inpoint=None, outpoint=None, metadata=None
    ):
        self.files.append(
            self.FileItem(filepath, duration, inpoint, outpoint, metadata)
        )

    def add_files(self, files):
        for file in files:
            self.files.append(self.FileItem(file))

    def add_glob(self, expr):
        raise ValueError("TODO")

    def add_sequence(self, expr):
        raise ValueError("TODO")

    def add_stream(self, id=None, codec=None, metadata=None, extradata=None):
        self.streams.append(self.StreamItem(id, codec, metadata, extradata))

    def add_option(self, key, value):
        self.options[key] = value

    def add_options(self, options):
        self.options.update(options)

    def add_chapter(self, id, start, end):
        self.chapters[id] = (start, end)

    def parse(self, script, append=False):
        def new_file(args):
            self.files.append(self.FileItem(unescape(args)))

        def new_stream(_):
            self.streams.append(self.StreamItem())

        def set_file_attr(key, args):
            setattr(self.last_file, key, args)

        def set_file_meta(esc, args):
            k, v = args.split(esc, 1)
            self.last_file.metadata[k] = unescape(v)

        def set_stream_attr(key, args):
            setattr(self.last_stream, key, args)

        def set_stream_meta(args):
            k, v = args.split(" ", 1)
            self.last_stream.metadata[k] = unescape(v)

        def set_option(args):
            key, value = args.split(" ", 1)
            self.options[key] = unescape(value)

        def set_chapter(args):
            id, start, end = args.split(" ", 2)
            self.chapters[unescape(id)] = (start, end)

        arg_parsers = {
            "file": new_file,
            "duration": partial(set_file_attr, "duration"),
            "inpoint": partial(set_file_attr, "inpoint"),
            "outpoint": partial(set_file_attr, "outpoint"),
            "file_packet_metadata": partial(set_file_meta, "="),
            "file_packet_meta": partial(set_file_meta, " "),
            "option": set_option,
            "stream": new_stream,
            "exact_stream_id": partial(set_stream_attr, "id"),
            "stream_meta": set_stream_meta,
            "stream_codec": partial(set_stream_attr, "codec"),
            "stream_extradata": partial(set_stream_attr, "extradata"),
            "chapter": set_chapter,
        }

        if not append:
            self.files = []
            self.streams = []
            self.options = {}
            self.chapters = {}

        for match in re.finditer(r"\s*([^#]\S*)\s+(.*)?\n", script):
            dir = match[1]
            args = match[2]

            if dir == "ffconcat" and args == "version 1.0":
                continue

            try:
                arg_parsers[dir](args)
            except:
                raise ValueError(f"Unknown directive or invalid syntax: {dir} {args}")

    def compose(self, f=None):
        if f is None:
            f = io.StringIO()

        f.write("ffconcat version 1.0\n")

        for file in self.files:
            f.writelines(file.lines)

        for key, value in self.options.items():
            f.write(f"option {key} {escape(value)}\n")

        for stream in self.streams:
            f.writelines(stream.lines)

        for id, start, end in sorted(
            ((key, *value) for key, value in self.chapters.items()),
            key=lambda el: el[1],
        ):
            f.write(f"chapter {escape(id)} {start} {end}\n")
        return f

    def __enter__(self):
        self._temp_file = self.compose(
            None if self.pipe_url else NamedTemporaryFile("w+t")
        )

        return self

    def update(self):
        """Update the prepared script for the context
        """        
        if self._temp_file:
            self._temp_file.close()
            self._temp_file = self.compose(
                None if self.pipe_url else NamedTemporaryFile("w+t")
            )


    def __exit__(self, *exc):
        self._temp_file.close()
        self._temp_file = None

    @property
    def url(self):
        """:str: url to use as FFmpeg `-i` option"""
        try:
            return self.pipe_url or self._temp_file.name
        except:
            return "unset"

    @property
    def input(self):
        """:str: composed concat listing script"""
        return (self._temp_file or self.compose()).getvalue()

    def __str__(self) -> str:
        return self.url

    def __repr__(self) -> str:
        script = "\n        ".join(self.input.splitlines())
        return f"""FFmpeg concat demuxer source generator
    url: {self.url}
    script:
        {script}"""
