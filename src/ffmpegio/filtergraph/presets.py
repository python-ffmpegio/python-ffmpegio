"""ffmpegio.filtergraph.presets Module - a collection of preset filtergraph generators"""

from __future__ import annotations

from fractions import Fraction
from functools import reduce

from .. import filtergraph as fgb
from .._typing import TYPE_CHECKING, Any, Literal, Sequence
from ..path import check_version
from ..stream_spec import StreamSpecDict
from .abc import FilterGraphObject

if TYPE_CHECKING:
    from .Chain import Chain
    from .Graph import Graph


def remove_alpha(
    fill_color: str,
    pix_fmt: str | None = None,
    *,
    input_label: str | None = None,
    output_label: str | None = None,
) -> Graph:
    """generate a filter graph to remove alpha channel from a video

    :param fill_color: _description_
    :param input_label: _description_, defaults to None
    :param output_label: _description_, defaults to None
    :return: Resulting filter graph in the form:

        ```
        color,[in]scale2ref[main],[main]overlay[out]
        ```

    """

    if input_label is None:
        input_label = "in"
    if output_label is None:
        output_label = "out"

    if check_version("7.1.0", "<"):
        expr = f"color=c={fill_color}[cout],[cout]scale2ref[l2],[l2]overlay=shortest=1"
        inpad = (0, 1, 1)
        outpad = (0, 2, 0)
    else:
        expr = (
            "split[in1][in2];"
            f"color=c={fill_color}[cout];"
            "[cout][in1]scale=rw:rh[sout];"
            "[sout][in2]overlay=shortest=1"
        )
        inpad = (0, 0, 0)
        outpad = (3, 0, 0)

    fg = fgb.Graph(expr)

    if pix_fmt is not None:
        fg += fgb.format(pix_fmts=pix_fmt)
        outpad = (outpad[0], outpad[1] + 1, 0)

    fg.add_label(input_label, inpad)
    fg.add_label(output_label, outpad=outpad)

    return fg


def filter_video_basic(
    scale: str | Sequence | None = None,
    crop: str | Sequence | None = None,
    flip: Literal["horizontal", "vertical", "both"] | None = None,
    transpose: str | Sequence | None = None,
) -> Chain:

    vfilters = []

    if crop:
        try:
            assert not isinstance(crop, str)
            vfilters.append(fgb.crop(*crop))
        except:
            vfilters.append(fgb.crop(crop))

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
            vfilters.append(fgb.transpose(*transpose))
        except:
            vfilters.append(fgb.transpose(transpose))

    if scale:
        try:
            scale = [int(s) for s in scale.split("x")]
        except:
            pass
        try:
            assert not isinstance(scale, str)
            vfilters.append(fgb.scale(*scale))
        except:
            vfilters.append(fgb.scale(scale))

    return sum(vfilters, start=fgb.Chain())


def square_pixels(
    mode: Literal["upscale", "downscale", "upscale_even", "downscale_even"],
) -> Chain:
    """a filter chain to square pixels of video frames

    :param mode: whether to 'upscale' by preserving the long side and elongating
                 the short side or 'downscale' by preserving the short side and
                 shrinking the long side. Both modes can be made to force an even
                 numbered frame size to accommodate video codecs like h264.
    :return: a chain of `scale` and `setsar` filters
    """
    try:
        expr = {
            "upscale": "scale='max(iw,ih*dar)':'max(iw/dar,ih)':eval=init,setsar=1/1",
            "downscale": "scale='min(iw,ih*dar)':'min(iw/dar,ih)':eval=init,setsar=1/1",
            "upscale_even": "scale='trunc(max(iw,ih*dar)/2)*2':'trunc(max(iw/dar,ih)/2)*2':eval=init,setsar=1/1",
            "downscale_even": "scale='trunc(min(iw,ih*dar)/2)*2':'trunc(min(iw/dar,ih)/2)*2':eval=init,setsar=1/1",
        }[mode]
    except KeyError as e:
        raise ValueError(f"unknown mode: {mode}") from e

    return fgb.Chain(expr)


def merge_audio(
    streams: dict[StreamSpecDict, dict[str, Any]],
    output_ar: int | None = None,
    output_sample_fmt: str | None = None,
    output_pad_label: str | None = "aout",
) -> Graph:
    """Create a filtergraph to merge input audio streams.

    This preset filtergraph formats the input streams so that their sampling rates and sample formats are first converted
    to the same satisfying the requirements of the `amerge` filter.

    :param streams: List of input audio streams to merge. Each stream is keyed by its FFmpeg stream specifier and must provide its input options.
                    The option must include the sampling rate (`ar`) and sample format (`sample_fmt`).
    :param output_ar: Sampling rate of the merged audio stream in samples/second, defaults to None to use the sampling rate of the first input stream
    :param output_sample_fmt: Sample format of the merged audio stream, defaults to None to use the sample format of the first input stream
    :param output_pad_label: label of the `amerge` filter output, defaults to None to leave the output pad unconnected

    """

    # number of input audio streams to be merged
    n_ain = len(streams)

    # if output sampling rate or sample format not given, use the first stream's setting
    if output_ar is None or output_sample_fmt is None:
        opts = next(iter(streams.values()))
        if output_ar is None:
            output_ar = opts["ar"]
        if output_sample_fmt is None:
            output_sample_fmt = opts["sample_fmt"]

    # build complex_filter to merge

    def match_sample(sspec, opts):
        fopts = {}
        if opts["ar"] != output_ar:
            fopts["r"] = output_ar
        if opts["sample_fmt"] != output_sample_fmt:
            fopts["f"] = output_sample_fmt

        in_label = f"[{sspec}]"
        return (in_label >> fgb.aformat(**fopts)) if len(fopts) else in_label

    afilt = [match_sample(*st) for st in streams.items()] >> fgb.amerge(inputs=n_ain)

    return (afilt >> output_pad_label) if output_pad_label else afilt


def temp_video_src(r: int | Fraction, pix_fmt: str, s: tuple[int, int]) -> fgb.Chain:
    """temporary video source

    :param r: frame rate
    :param pix_fmt: pixel format
    :param s: frame shape (width x height)
    :return: a chain of color and format filters
    """
    fg = fgb.color(s=f"{s[0]}x{s[1]}", r=r)
    return fg if pix_fmt == "unknown" else (fg + fgb.format(pix_fmts=pix_fmt))


def temp_audio_src(ar: int, sample_fmt: str, ac: int) -> fgb.Chain:
    """temporary audio source

    :param ar: sampling rate
    :param sample_fmt: sample format
    :param ac: number of channels
    :return: a chain of aevalsrc and aformat
    """
    return fgb.aevalsrc("|".join(["0"] * ac)) + fgb.aformat(
        sample_fmts=sample_fmt or "dbl", r=ar
    )
