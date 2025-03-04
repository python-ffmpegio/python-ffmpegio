"""ffmpegio plugin to use `numpy.ndarray` objects for media data I/O"""

import matplotlib as Figure
from pluggy import HookimplMarker
from typing import Tuple
import io

__all__ = ["video_info", "video_bytes"]

hookimpl = HookimplMarker("ffmpegio")


@hookimpl
def video_info(obj: Figure) -> Tuple[Tuple[int, int, int], str]:
    """get video frame info

    :param obj: matplotlib Figure object
    :return shape: shape (height,width,components)
    :return dtype: data type in numpy dtype str expression
    """
    try:
        return (int(obj.bbox.bounds[3]), int(obj.bbox.bounds[2]), 4), "|u1"
    except:
        return None


@hookimpl
def video_bytes(obj: Figure) -> memoryview:
    """return bytes-like object of rawvideo NumPy array

    :param obj: video frame data with arbitrary number of frames
    :return: memoryview of video frames
    """

    try:
        with io.BytesIO() as io_buf:
            obj.savefig(io_buf, format="raw")
            io_buf.seek(0)
            return io_buf.getvalue()
    except:
        None
