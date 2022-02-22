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
