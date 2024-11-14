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
        message="ffmpegio-core distribution package has been deprecated and consolidated to ffmpegio package since v0.11.0. Please uninstall ffmpegio-core and install only the ffmpegio package to receive future updates."
    )
