import numpy as np
import fractions, re
from .. import utils

# https://docs.microsoft.com/en-us/previous-versions//dd183376(v=vs.85)?redirectedfrom=MSDN


def decode_avih(data, prev_chunk):
    AVIF_COPYRIGHTED = int("0x00020000", 0)
    AVIF_HASINDEX = int("0x00000010", 0)
    AVIF_ISINTERLEAVED = int("0x00000100", 0)
    AVIF_MUSTUSEINDEX = int("0x00000020", 0)
    AVIF_WASCAPTUREFILE = int("0x00010000", 0)
    vals = np.frombuffer(data, dtype=np.uint32)
    flags = vals[3]
    return dict(
        micro_sec_per_frame=vals[0],
        max_bytes_per_sec=vals[1],
        padding_granularity=vals[2],
        flags=dict(
            copyrighted=bool(flags & AVIF_COPYRIGHTED),
            has_index=bool(flags & AVIF_HASINDEX),
            is_interleaved=bool(flags & AVIF_ISINTERLEAVED),
            must_use_index=bool(flags & AVIF_MUSTUSEINDEX),
            was_capture_file=bool(flags & AVIF_WASCAPTUREFILE),
        ),
        total_frames=vals[4],
        initial_frames=vals[5],
        streams=vals[6],
        suggested_buffer_size=vals[7],
        width=vals[8],
        height=vals[9],
    )


def decode_strh(data, prev_chunk):
    AVISF_DISABLED = int("0x00000001", 0)
    AVISF_VIDEO_PALCHANGES = int("0x00010000", 0)
    flags = int.from_bytes(data[8:12], byteorder="little", signed=False)
    vals = np.frombuffer(data[16:-8], dtype=np.uint32)
    rect = np.frombuffer(data[-8:], dtype=np.int16)
    return dict(
        fcc_type=data[:4].decode("utf-8"),
        fcc_handler=data[4:8].decode("utf-8"),
        # fcc_handler=int.from_bytes(data[4:8], byteorder="little", signed=False),
        flags=dict(
            video_pal_changes=bool(flags & AVISF_VIDEO_PALCHANGES),
            disabled=bool(flags & AVISF_DISABLED),
        ),
        priority=int.from_bytes(data[12:14], byteorder="little", signed=False),
        language=int.from_bytes(data[14:16], byteorder="little", signed=False),
        initial_frames=vals[0],
        scale=vals[1],
        rate=vals[2],
        start=vals[3],
        length=vals[4],
        suggested_buffer_size=vals[5],
        quality=vals[6],
        sample_size=vals[7],
        frame_left=rect[0],
        frame_top=rect[1],
        frame_right=rect[2],
        frame_bottom=rect[3],
    )


# PCM audio
WAVE_FORMAT_PCM = 1
# IEEE floating-point audio
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = int("FFFE", 16)  # /* Microsoft */


def decode_strf(data, prev_chunk):
    fcc_type = prev_chunk[1]["fcc_type"]
    if fcc_type == "vids":  # BITMAPINFO
        # fmt = data[16:20].decode("utf-8")
        # fmt = int.from_bytes(data[16:20], byteorder="little", signed=False)
        # if data[16] == 0:
        #     fmt = "rgb24"
        # else:
        fmt = data[16]
        return dict(
            size=int.from_bytes(data[:4], byteorder="little", signed=False),
            width=int.from_bytes(data[4:8], byteorder="little", signed=True),
            height=int.from_bytes(data[8:12], byteorder="little", signed=True),
            planes=int.from_bytes(data[12:14], byteorder="little", signed=False),
            bit_count=int.from_bytes(data[14:16], byteorder="little", signed=False),
            compression=data[16:20].decode("utf-8") if fmt >= 4 else fmt,
            size_image=int.from_bytes(data[20:24], byteorder="little", signed=False),
            x_pels_per_meter=int.from_bytes(
                data[24:28], byteorder="little", signed=True
            ),
            y_pels_per_meter=int.from_bytes(
                data[28:32], byteorder="little", signed=True
            ),
            clr_used=int.from_bytes(data[32:36], byteorder="little", signed=False),
            clr_important=int.from_bytes(data[36:], byteorder="little", signed=False),
        )
    elif fcc_type == "auds":  # WAVEFORMATEX
        d = dict(
            format_tag=int.from_bytes(data[:2], byteorder="little", signed=False),
            channels=int.from_bytes(data[2:4], byteorder="little", signed=False),
            samples_per_sec=int.from_bytes(data[4:8], byteorder="little", signed=False),
            avg_bytes_per_sec=int.from_bytes(
                data[8:12], byteorder="little", signed=False
            ),
            block_align=int.from_bytes(data[12:14], byteorder="little", signed=False),
            bits_per_sample=int.from_bytes(
                data[14:16], byteorder="little", signed=False
            ),
        )
        if d["format_tag"] == WAVE_FORMAT_EXTENSIBLE:
            d["samples"] = int.from_bytes(data[16:18], byteorder="little", signed=False)
            d["channel_mask"] = int.from_bytes(
                data[18:20], byteorder="little", signed=False
            )
            d["subformat"] = int.from_bytes(
                data[20:22], byteorder="little", signed=False
            )
            # print(int.from_bytes(data[16:18], byteorder="little", signed=False))
            # print("strf-waveform", len(data))
        return d
    return data


def decode_zstr(data, prev_chunk):
    return data[:-1].decode("utf-8")


def decode_vprp(data, prev_chunk):
    vals = np.frombuffer(data, dtype=np.uint32)

    def field_desc(vals):
        return dict(
            compressed_bm_height=vals[0],
            compressed_bm_width=vals[1],
            valid_bm_height=vals[2],
            valid_bm_width=vals[3],
            valid_bmx_offset=vals[4],
            valid_bmy_offset=vals[5],
            video_x_offset_in_t=vals[6],
            video_y_valid_start_line=vals[7],
        )

    return dict(
        video_format_token=vals[0],
        video_standard=vals[1],
        vertical_refresh_rate=vals[2],
        h_total_in_t=vals[3],
        v_total_in_lines=vals[4],
        frame_aspect_ratio=fractions.Fraction(
            int.from_bytes(data[22:24], byteorder="little", signed=False),
            int.from_bytes(data[20:22], byteorder="little", signed=False),
        ),
        frame_width_in_pixels=vals[6],
        frame_height_in_lines=vals[7],
        field_per_frame=vals[8],
        field_info=tuple(
            (field_desc(vals[9 + i * 8 : 17 + i * 8]) for i in range(int(vals[8])))
        ),
    )


def decode_dmlh(data, prev_chunk):
    return dict(total_frames=int.from_bytes(data, byteorder="little", signed=False))


decoders = dict(
    avih=decode_avih,
    strh=decode_strh,
    strf=decode_strf,
    strn=decode_zstr,
    vprp=decode_vprp,
    ISMP=decode_zstr,
    IDIT=decode_zstr,
    IARL=decode_zstr,
    IART=decode_zstr,
    ICMS=decode_zstr,
    ICMT=decode_zstr,
    ICOP=decode_zstr,
    ICRD=decode_zstr,
    ICRP=decode_zstr,
    IDIM=decode_zstr,
    IDPI=decode_zstr,
    IENG=decode_zstr,
    IGNR=decode_zstr,
    IKEY=decode_zstr,
    ILGT=decode_zstr,
    IMED=decode_zstr,
    INAM=decode_zstr,
    IPLT=decode_zstr,
    IPRD=decode_zstr,
    ISBJ=decode_zstr,
    ISFT=decode_zstr,
    ISHP=decode_zstr,
    ISRC=decode_zstr,
    ISRF=decode_zstr,
    ITCH=decode_zstr,
)

# tcdl
# time
# indx


def next_chunk(f, resolve_sublist=False, prev_item=None):
    b = f.read(4)
    if not len(b):
        return None

    id = b.decode("utf-8")
    datasize = int.from_bytes(f.read(4), byteorder="little", signed=False)
    size = datasize + 1 if datasize % 2 else datasize

    if id == "LIST":
        data = f.read(4).decode("utf-8")
        listsize = size - 4
        if resolve_sublist or data == "INFO":
            items = []
            while listsize:
                item = next_chunk(f, resolve_sublist, prev_item)
                if item[0] != "JUNK":
                    items.append(item[:-1])
                    prev_item = item
                listsize -= item[2] + 8
            id = data
            data = items
    elif id == "JUNK":
        f.read(size)
        if size > datasize:
            f.read(size - datasize)
        data = None
    else:
        data = f.read(datasize)
        if size > datasize:
            f.read(size - datasize)
        decoder = decoders.get(id, None)
        if decoder:
            data = decoder(data, prev_item)
    return id, data, size


fcc_types = dict(vids="v", auds="a", txts="s")  # , mids="midi")


def read_header(f, use_ya8):
    f.read(12)  # ignore the 'RIFF SIZE AVI ' entry of the top level chunk
    hdr = next_chunk(f, resolve_sublist=True)[1]
    ch = next_chunk(f)
    while ch and ch[0] != "LIST" and ch[1] != "movi":
        ch = next_chunk(f)

    def get_stream_info(i, data, use_ya8):
        strh = data[0][1]
        strf = data[1][1]
        type = fcc_types[strh["fcc_type"]]  # raises if not valid type
        info = dict(index=i, type=type)
        if type == fcc_types["vids"]:
            info["frame_rate"] = fractions.Fraction(strh["rate"], strh["scale"])
            info["width"] = strf["width"]
            info["height"] = abs(strf["height"])
            bpp = strf["bit_count"]
            compression = strf["compression"]
            # force unsupported pixel formats
            info["pix_fmt"] = (
                {"Y800": "gray", "RGBA": "rgba"}.get(compression, None)
                if isinstance(compression, str)
                else (compression, bpp)
                if compression
                else "rgb48le"
                if bpp == 48
                else "grayf32le"
                if bpp == 32
                else "rgb24"
                if bpp == 24
                else "ya8"
                if use_ya8
                else "gray16le"
                if bpp == 16
                else None
            )
            vprp = next((d[1] for d in data[2:] if d[0] == "vprp"), None)
            info["dar"] = vprp["frame_aspect_ratio"] if vprp else None
        elif type == fcc_types["auds"]:  #'audio'
            info["sample_rate"] = strf["samples_per_sec"]
            info["channels"] = strf["channels"]

            strf_format = (
                strf["format_tag"]
                if strf["format_tag"] != WAVE_FORMAT_EXTENSIBLE
                else strf["subformat"],
                strf["bits_per_sample"],
            )

            info["sample_fmt"] = {
                (WAVE_FORMAT_PCM, 8): "u8",
                (WAVE_FORMAT_PCM, 16): "s16",
                (WAVE_FORMAT_PCM, 32): "s32",
                (WAVE_FORMAT_IEEE_FLOAT, 32): "flt",
                (WAVE_FORMAT_IEEE_FLOAT, 64): "dbl",
            }.get(strf_format, strf_format)
            # TODO: if need arises, resolve more formats, need to include codec names though
        return info

    strl = [hdr[i][1] for i in range(len(hdr)) if hdr[i][0] == "strl"]
    return [get_stream_info(i, strl[i], use_ya8) for i in range(len(strl))]


def read_frame(f):
    chunk = next_chunk(f)
    if chunk is None or not re.match(r"ix..|\d{2}(?:wb|db|dc|tx|pc)", chunk[0]):
        return None
    hdr = chunk[0]
    return (int(hdr[:2]) if hdr[2:] in ("wb", "db", "dc", "tx") else None), chunk[1]


#######################################################################################################


class AviReader:
    def __init__(self, use_ya8=False):
        self._f = None
        self.use_ya8 = use_ya8  #: bool: True to interpret 16-bit pixel as 'ya8' pix_fmt, False for 'gray16le'

        self.ready = False  #:bool: True if AVI headers has been processed
        self.streams = None  #:dict: Stream headers keyed by stream id (int key)
        self.converters = None  #:dict : Stream to numpy ndarray conversion functions keyed by stream id

    def start(self, f):
        self._f = f
        hdr = read_header(self._f, self.use_ya8)

        cnt = {"v": 0, "a": 0, "s": 0}

        def set_stream_info(hdr):
            st_type = hdr["type"]
            id = cnt[st_type]
            cnt[st_type] += 1
            if st_type == "v":
                _, ncomp, dtype, _ = utils.get_pixel_config(hdr["pix_fmt"])
                shape = (hdr["height"], hdr["width"], ncomp)
            elif st_type == "a":
                _, dtype = utils.get_audio_format(hdr["sample_fmt"])
                shape = (hdr["channels"],)
            return {
                "spec": utils.spec_stream(id, st_type),
                "shape": shape,
                "dtype": dtype,
                **hdr,
            }

        self.streams = {v["index"]: set_stream_info(v) for v in hdr}

        def get_converter(stream):
            return lambda b: np.frombuffer(b, dtype=stream["dtype"]).reshape(
                -1, *stream["shape"]
            )

        self.converters = {k: get_converter(v) for k, v in self.streams.items()}

        self.ready = True

    def __next__(self):
        i = d = None
        while i is None:  # None if unknown frame format, skip
            frame = read_frame(self._f)
            if frame is None:  # likely eof
                raise StopIteration
            i, d = frame
        return i, self.converters[i](d)

    def __iter__(self):
        return self


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
