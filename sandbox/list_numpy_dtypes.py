import numpy as np

# ['|u1', '<u2', '<i2','<i4', '<i8', '<f2', '<f4', '<f8']

print(
    [
        np.dtype(dtype).str
        for dtype in set(
            (
                np.uint8,
                np.uint16,
                np.float32,
                np.uint8,
                np.uint16,
                np.uint8,
                np.uint16,
                np.uint8,
                np.uint8,
                np.int16,
                np.int32,
                np.int64,
                np.float32,
                np.float64,
            )
        )
    ]
)
