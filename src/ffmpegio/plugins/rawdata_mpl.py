"""ffmpegio plugin to use `numpy.ndarray` objects for media data I/O"""

import matplotlib as Figure
from pluggy import HookimplMarker
from typing import Tuple
import io

hookimpl = HookimplMarker("ffmpegio")

__version__ = "0.1.1"


@hookimpl
def video_info(obj: Figure) -> Tuple[Tuple[int, int, int], str]:
    """get video frame info

    :param obj: matplotlib Figure object
    :type obj: Figure
    :return: shape (height,width,4) and data type "|u1" (rgba)
    :rtype: Tuple[Tuple[int, int, int], str]
    """
    try:
        return (int(obj.bbox.bounds[3]), int(obj.bbox.bounds[2]), 4), "|u1"
    except:
        return None


@hookimpl
def video_bytes(obj: Figure) -> memoryview:
    """return bytes-like object of rawvideo NumPy array

    :param obj: video frame data with arbitrary number of frames
    :type obj: Figure
    :return: memoryview of video frames
    :rtype: memoryview
    """

    try:
        with io.BytesIO() as io_buf:
            obj.savefig(io_buf, format="raw")
            io_buf.seek(0)
            return io_buf.getvalue()
    except:
        None
        