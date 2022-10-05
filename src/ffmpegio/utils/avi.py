from io import SEEK_CUR
import fractions, re
from struct import Struct
from collections import namedtuple
from itertools import accumulate

from ..utils import get_video_format, get_audio_format, stream_spec, get_samplesize
from .. import plugins

# https://docs.microsoft.com/en-us/previous-versions//dd183376(v=vs.85)?redirectedfrom=MSDN


class FlagProcessor:
    def __init__(self, name, flags, masks, defaults):
        self.template = namedtuple(
            name,
            flags,
            defaults=defaults,
        )
        self.masks = self.template._make(masks)

    def default(self):
        return self.template()

    def unpack(self, flags):
        return self.template._make((bool(flags & mask) for mask in self.masks))

    def pack(self, flags):
        return sum((mask if flag else 0 for flag, mask in zip(flags, self.masks)))


class StructProcessor:
    def __init__(self, name, format, fields, defaults=None, **flags):
        if "S" in format or "C" in format:
            # expand the format
            m = re.match(r"([<>!=])?(.+)", format)
            fmt_items = [
                (int(m[1]) if m[1] else 1, m[2])
                for m in re.finditer(r"(\d*)([xcCbB?hHiIlLqQnNefdsSpP])", m[2])
            ]
            fmt_counts = [1 if f in "sSp" else count for count, f in fmt_items]
            fmt_offsets = list((0, *accumulate(fmt_counts)))
            is_str = [False] * fmt_offsets[-1]
            for itm, offset in zip(fmt_items, fmt_offsets[:-1]):
                is_str[offset] = itm[1] in "SC"
            self.is_str = [fields[i] for i, tf in enumerate(is_str) if tf]
            format = format.replace("C", "c").replace("S", "s")
        else:
            self.is_str = ()

        self.struct = Struct(format)
        self.template = namedtuple(name, fields, defaults=defaults)
        self.flags = ((k, FlagProcessor(*v)) for k, v in flags.items())

    def default(self):
        data = self.template()
        return data._replace(**{k: proc.default() for k, proc in self.flags})

    def _unpack(self, data):
        data = self.template._make(data)
        return data._replace(
            **{field: getattr(data, field).decode("utf-8") for field in self.is_str},
            **{k: proc.unpack(getattr(data, k)) for k, proc in self.flags},
        )

    def unpack(self, buffer):
        return self._unpack(self.struct.unpack(buffer))

    def unpack_from(self, buffer, offset=0):
        return self._unpack(self.struct.unpack_from(buffer, offset))

    def _pack(self, ntuple):
        return ntuple._replace(
            **{k: proc.pack(getattr(ntuple, k)) for k, proc in self.flags},
            **{field: ntuple[field].encode("utf-8") for field in self.is_str},
        )

    def pack(self, ntuple):
        return self.struct.pack(*self._pack(ntuple))

    def pack_into(self, buffer, offset, ntuple):
        self.struct.pack_into(buffer, offset, *self._pack(ntuple))

    @property
    def size(self):
        return self.struct.size


AVIMainHeader = StructProcessor(
    "Avih",
    "<10I",
    (
        "micro_sec_per_frame",
        "max_bytes_per_sec",
        "padding_granularity",
        "flags",
        "total_frames",
        "initial_frames",
        "streams",
        "suggested_buffer_size",
        "width",
        "height",
    ),
    (0,) * 10,
    flags=(
        "AvihFlags",
        (
            "copyrighted",
            "has_index",
            "is_interleaved",
            "must_use_index",
            "was_capture_file",
        ),
        (
            int("0x00020000", 0),
            int("0x00000010", 0),
            int("0x00000100", 0),
            int("0x00000020", 0),
            int("0x00010000", 0),
        ),
        (False,) * 5,
    ),
)


AVIStreamHeader = StructProcessor(
    "AVISTREAMHEADER",
    "<4S4SI2H8I4h",
    (
        "fcc_type",  # 'auds','mids','txts','vids'
        "fcc_handler",
        "flags",
        "priority",
        "language",
        "initial_frame",
        "scale",
        "rate",
        "start",
        "length",
        "suggested_buffer_size",
        "quality",
        "sample_size",
        "frame_left",
        "frame_top",
        "frame_right",
        "frame_bottom",
    ),
    (b"\0" * 4, b"\0" * 4, *((0,) * 15)),
    flags=(
        "StrhFlags",
        (
            "video_pal_changes",
            "disabled",
        ),
        (
            int("0x00000001", 0),
            int("0x00010000", 0),
        ),
        (False,) * 2,
    ),
)

# PCM audio
WAVE_FORMAT_PCM = 1
# IEEE floating-point audio
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = int("FFFE", 16)  # /* Microsoft, 65534 */

BitmapInfoHeader = StructProcessor(
    "BITMAPINFOHEADER",
    "IiiHH4sIiiII",
    (
        "size",
        "width",
        "height",
        "planes",
        "bit_count",
        "compression",  # convert to str if 1st byte is >=4
        "size_image",
        "x_pels_per_meter",
        "y_pels_per_meter",
        "clr_used",
        "clr_important",
    ),
    (0,) * 11,
)

WaveFormatEx = StructProcessor(
    "WAVEFORMATEX",
    "HHIIHH",
    (
        "format_tag",
        "channels",
        "samples_per_sec",
        "avg_bytes_per_sec",
        "block_align",
        "bits_per_sample",
    ),
    (0,) * 6,
)

WaveFormatExtensible = StructProcessor(
    "WAVEFORMATEXTENSIBLE",
    "HHIH14s",
    (
        "size",
        "samples",
        "channel_mask",
        "sub_format_wave",
        "sub_format_rest",
    ),
    (*((0,) * 3), 0, "\0" * 14),
)


VideoPropHeader = StructProcessor(
    "VPRP",
    "5IHH3I",
    (
        "video_format_token",
        "video_standard",
        "vertical_refresh_rate",
        "h_total_in_t",
        "v_total_in_lines",
        "frame_aspect_ratio_y",
        "frame_aspect_ratio_x",
        "frame_width_in_pixels",
        "frame_height_in_lines",
        "field_per_frame",
    ),
    ((0,) * 10),
)

VPRP_VideoField = StructProcessor(
    "VPRP_VIDEO_FIELD_DESC",
    "8I",
    (
        "compressed_bm_height",
        "compressed_bm_width",
        "valid_bm_height",
        "valid_bm_width",
        "valid_bm_x_offset",
        "valid_bm_y_offset",
        "video_x_offset_in_t",
        "video_y_valid_start_line",
    ),
    ((0,) * 8),
)


ChunkHeader = StructProcessor("CHDR", "<4SI", ("id", "datasize"))


fcc_types = dict(vids="v", auds="a", txts="s")  # , mids="midi")


def read_chunk_header(f):
    b = f.read(ChunkHeader.size)
    id, datasize = ChunkHeader.unpack(b)
    list_type = None
    if id in ("RIFF", "LIST"):
        list_type = f.read(4).decode("utf-8")
        datasize -= 4
    chunksize = datasize + 1 if datasize % 2 else datasize
    return id, datasize, chunksize, list_type


def get_chunk_header(b, offset=0):
    id, datasize = ChunkHeader.unpack_from(b, offset)
    offset += ChunkHeader.size
    list_type = None
    if id in ("RIFF", "LIST"):
        list_type = b[offset : offset + 4].decode("utf-8")
        offset += 4
        datasize -= 4
    chunksize = datasize + 1 if datasize % 2 else datasize
    return offset, chunksize, id, list_type


def get_stream_header(b, offset, end):
    data = {}

    offset, chunksize, id, _ = get_chunk_header(b, offset)
    data[id] = strh = AVIStreamHeader.unpack_from(b, offset)
    offset += chunksize

    offset, chunksize, id, _ = get_chunk_header(b, offset)
    if strh.fcc_type == "vids":
        data[id] = BitmapInfoHeader.unpack_from(b, offset)

        # if 1st byte is a readable ascii char
        compression = data[id].compression
        comp_val = compression[0]
        data[id] = data[id]._replace(
            compression=comp_val if comp_val < 32 else compression.decode("utf-8")
        )

        # offset += chunksize
        # while offset < end:
        #     offset, chunksize, id, _ = get_chunk_header(b, offset)
        #     if id == "vprp":
        #         vprp = VideoPropHeader.unpack_from(b, offset)
        #         offset += VideoPropHeader.size
        #         ninfo = VPRP_VideoField.size
        #         field_info = [
        #             VPRP_VideoField.unpack_from(b, i)
        #             for i in range(offset, offset + ninfo * vprp.field_per_frame, ninfo)
        #         ]
        #         data[id] = namedtuple(
        #             type(vprp).__name__, (*vprp._fields, "field_info")
        #         )(*vprp, field_info)
        #         break
        #     else:
        #         offset += chunksize

    elif strh.fcc_type == "auds":
        strf = WaveFormatEx.unpack_from(b, offset)
        if strf.format_tag == WAVE_FORMAT_EXTENSIBLE:
            strfext = WaveFormatExtensible.unpack_from(b, offset + WaveFormatEx.size)
            strf = namedtuple(
                type(strfext).__name__, (*strf._fields, *strfext._fields)
            )(strfext.sub_format_wave, *strf[1:], *strfext)
        data[id] = strf
    else:
        raise RuntimeError(f"Unsupported stream type: {strh.fcc_type}")

    return data


def _seek(f, n):
    try:
        f.seek(n, SEEK_CUR)
    except:
        f.read(n)


def read_header(f, pix_fmt=None):

    # read the RIFF header
    id, datasize, chunksize, list_type = read_chunk_header(f)
    if id != "RIFF" or list_type != "AVI ":
        raise RuntimeError(f"File stream is not AVI")

    # read the hdrl chunk
    id, datasize, chunksize, list_type = read_chunk_header(f)
    if id != "LIST" and list_type != "hdrl":
        raise RuntimeError(f"AVI is missing header chunk")
    b = f.read(datasize)
    if chunksize > datasize:
        _seek(f, 1)

    # read until encountering the movi list
    while True:
        id, _, chunksize, list_type = read_chunk_header(f)
        if list_type == "movi":
            break
        _seek(f, chunksize)

    # parse hdrl LIST chunk
    offset, chunksize, id, list_type = get_chunk_header(b)
    if id != "avih":
        raise RuntimeError("missing avi chunk")
    avih = AVIMainHeader.unpack_from(b, offset)
    offset += chunksize
    streams = []
    while True:
        try:
            offset, chunksize, id, list_type = get_chunk_header(b, offset)
        except:
            break
        if list_type != "strl":
            break

        streams.append(get_stream_header(b, offset, offset + chunksize))
        offset += chunksize

    def get_stream_info(i, strl, use_ya):
        strh = strl["strh"]
        strf = strl["strf"]
        type = fcc_types[strh.fcc_type]  # raises if not valid type
        info = dict(index=i, type=type)
        if type == fcc_types["vids"]:
            info["frame_rate"] = fractions.Fraction(strh.rate, strh.scale)
            info["width"] = strf.width
            info["height"] = abs(strf.height)
            bpp = strf.bit_count
            compression = strf.compression
            # force unsupported pixel formats
            info["pix_fmt"] = (
                {"Y800": "gray", "RGBA": "rgba"}.get(compression, None)
                if isinstance(compression, str)
                else (compression, bpp)
                if compression
                else "rgba64le"
                if bpp == 64
                else "rgb48le"
                if bpp == 48
                else ("ya16le" if use_ya else "grayf32le")
                if bpp == 32
                else "rgb24"
                if bpp == 24
                else ("ya8" if use_ya else "gray16le")
                if bpp == 16
                else None
            )
            # vprp = strl.get("vprp", None)
            # info["dar"] = (
            #     fractions.Fraction(vprp.frame_aspect_ratio_x, vprp.frame_aspect_ratio_y)
            #     if vprp
            #     else None
            # )
            info["dtype"], info["shape"] = get_video_format(
                info["pix_fmt"], (info["width"], info["height"])
            )
        elif type == fcc_types["auds"]:  #'audio'
            info["sample_rate"] = strf.samples_per_sec
            info["channels"] = strf.channels

            strf_format = (
                strf.format_tag,
                strf.bits_per_sample,
            )

            info["sample_fmt"] = {
                (WAVE_FORMAT_PCM, 8): "u8",
                (WAVE_FORMAT_PCM, 16): "s16",
                (WAVE_FORMAT_PCM, 32): "s32",
                (WAVE_FORMAT_PCM, 64): "s64",
                (WAVE_FORMAT_IEEE_FLOAT, 32): "flt",
                (WAVE_FORMAT_IEEE_FLOAT, 64): "dbl",
            }.get(strf_format, strf_format)
            # TODO: if need arises, resolve more formats, need to include codec names though
            info["dtype"], info["shape"] = get_audio_format(
                info["sample_fmt"], info["channels"]
            )
        return info

    return [get_stream_info(i, strl, pix_fmt) for i, strl in enumerate(streams)], (
        avih,
        streams,
    )


re_movi = re.compile(r"\d{2}(?:wb|db|dc|tx)")


def read_frame(f):
    while True:
        id, datasize, chunksize, list_type = read_chunk_header(f)
        if not list_type:
            m = re_movi.match(id)
            if m:  # data chunk found
                b = f.read(datasize)
                if chunksize > datasize:
                    _seek(f, chunksize - datasize)
                return int(id[:2]), b
            else:
                _seek(f, chunksize)

        id, datasize, chunksize, list_type = read_chunk_header(f)


#######################################################################################################


class AviReader:
    def __init__(self):
        self._f = None
        self.ready = False  #:bool: True if AVI headers has been processed
        self.streams = None  #:dict: Stream headers keyed by stream id (int key)
        self.itemsizes = None  #:dict: sample size of each stream in bytes

        hook = plugins.get_hook()
        self.converters = {"v": hook.bytes_to_video, "a": hook.bytes_to_audio}
        #:dict : bytes to media data object conversion functions keyed by stream type

    def start(self, f, pix_fmt=None):
        self._f = f
        hdr = read_header(self._f, pix_fmt)[0]

        cnt = {"v": 0, "a": 0, "s": 0}

        def set_stream_info(hdr):
            st_type = hdr["type"]
            id = cnt[st_type]
            cnt[st_type] += 1
            return {
                "spec": stream_spec(id, st_type),
                **hdr,
            }

        self.streams = {v["index"]: set_stream_info(v) for v in hdr}
        self.itemsizes = {
            v["index"]: get_samplesize(v["shape"], v["dtype"]) for v in hdr
        }
        self.ready = True

    def __next__(self):
        i = d = None
        while i is None:  # None if unknown frame format, skip
            try:
                i, d = read_frame(self._f)
            except:
                raise StopIteration
        return i, d

    def __iter__(self):
        return self

    def from_bytes(self, id, b):
        info = self.streams[id]
        return self.converters[info["type"]](
            b=b, dtype=info["dtype"], shape=info["shape"], squeeze=False
        )


# (
#     "hdrl",
#     [
#         (
#             "avih",
#             {
#                 "micro_sec_per_frame": 66733,
#                 "max_bytes_per_sec": 3974198,
#                 "padding_granularity": 0,
#                 "flags": 0,
#                 "total_frames": 0,
#                 "initial_frames": 0,
#                 "streams": 2,
#                 "suggested_buffer_size": 1048576,
#                 "width": 352,
#                 "height": 240,
#             },
#         ),
#         (
#             "strl",
#             [
#                 (
#                     "strh",
#                     {
#                         "fcc_type": "vids",
#                         "fcc_handler": "\x00\x00\x00\x00",
#                         "flags": 0,
#                         "priority": 0,
#                         "language": 0,
#                         "initial_frames": 0,
#                         "scale": 200,
#                         "rate": 2997,
#                         "start": 0,
#                         "length": 1073741824,
#                         "suggested_buffer_size": 1048576,
#                         "quality": 4294967295,
#                         "sample_size": 0,
#                         "frame_left": 0,
#                         "frame_top": 0,
#                         "frame_right": 352,
#                         "frame_bottom": 240,
#                     },
#                 ),
#                 (
#                     "strf",
#                     {
#                         "size": 40,
#                         "width": 352,
#                         "height": -240,
#                         "planes": 1,
#                         "bit_count": 24,
#                         "compression": "rgb24",
#                         "size_image": 253440,
#                         "x_pels_per_meter": 0,
#                         "y_pels_per_meter": 0,
#                         "clr_used": 0,
#                         "clr_important": 0,
#                     },
#                 ),
#                 (
#                     "vprp",
#                     {
#                         "video_format_token": 0,
#                         "video_standard": 0,
#                         "vertical_refresh_rate": 15,
#                         "h_total_in_t": 352,
#                         "v_total_in_lines": 240,
#                         "frame_aspect_ratio": Fraction(15, 22),
#                         "frame_width_in_pixels": 352,
#                         "frame_height_in_lines": 240,
#                         "field_per_frame": 1,
#                         "field_info": (
#                             {
#                                 "compressed_bm_height": 240,
#                                 "compressed_bm_width": 352,
#                                 "valid_bm_height": 240,
#                                 "valid_bm_width": 352,
#                                 "valid_bmx_offset": 0,
#                                 "valid_bmy_offset": 0,
#                                 "video_x_offset_in_t": 0,
#                                 "video_y_valid_start_line": 0,
#                             },
#                         ),
#                     },
#                 ),
#             ],
#         ),
#         (
#             "strl",
#             [
#                 (
#                     "strh",
#                     {
#                         "fcc_type": "auds",
#                         "fcc_handler": "\x01\x00\x00\x00",
#                         "flags": 0,
#                         "priority": 0,
#                         "language": 0,
#                         "initial_frames": 0,
#                         "scale": 1,
#                         "rate": 44100,
#                         "start": 0,
#                         "length": 1073741824,
#                         "suggested_buffer_size": 12288,
#                         "quality": 4294967295,
#                         "sample_size": 4,
#                         "frame_left": 0,
#                         "frame_top": 0,
#                         "frame_right": 0,
#                         "frame_bottom": 0,
#                     },
#                 ),
#                 (
#                     "strf",
#                     {
#                         "format_tag": 1,
#                         "channels": 2,
#                         "samples_per_sec": 44100,
#                         "avg_bytes_per_sec": 176400,
#                         "block_align": 4,
#                         "bits_per_sample": 16,
#                     },
#                 ),
#             ],
#         ),
#     ],
#     368,
# )
