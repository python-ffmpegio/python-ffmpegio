try:
    from math import prod
except:
    from functools import reduce
    from operator import mul

    prod = lambda seq: reduce(mul, seq, 1)


def dtype_itemsize(dtype):
    return int(dtype[-1])


def get_samplesize(shape, dtype):
    return prod(shape) * dtype_itemsize(dtype)


def deprecate_core():
    from importlib import metadata
    import warnings

    try:
        metadata.version("ffmpegio-core")
    except metadata.PackageNotFoundError:
        return

    warnings.warn(
        message="!!PACKAGE CONFLICT!! ffmpegio-core distribution package has been deprecated. Please read the following link for the instructions: https://github.com/python-ffmpegio/python-ffmpegio/wiki/Instructions-to-upgrade-to-v0.11.0."
    )
