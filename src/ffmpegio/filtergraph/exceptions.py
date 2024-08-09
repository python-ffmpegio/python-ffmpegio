from __future__ import annotations as _annotations

from ..errors import FFmpegioError


class FiltergraphConversionError(FFmpegioError): ...


class FilterOperatorTypeError(TypeError, FFmpegioError):
    def __init__(self, other) -> None:
        super().__init__(
            f"invalid filtergraph operation with an incompatible object of type {type(other)}"
        )


class FiltergraphMismatchError(TypeError, FFmpegioError):
    def __init__(self, n, m) -> None:
        super().__init__(
            f"cannot append mismatched filtergraphs: the first has {n} input "
            f"while the second has {m} outputs available."
        )


class FiltergraphInvalidIndex(TypeError, FFmpegioError):
    pass


class FiltergraphInvalidLabel(TypeError, FFmpegioError):
    pass


class FiltergraphInvalidExpression(TypeError, FFmpegioError):
    pass


class FiltergraphPadNotFoundError(FFmpegioError):
    ...
    # def __init__(self, type, index) -> None:
    #     target = (
    #         f"pad {index}"
    #         if isinstance(index, tuple)
    #         else f"label {index}" if isinstance(index, str) else f"filter {index}"
    #     )
    #     super().__init__(f"cannot find {type} pad at {target}")

class FiltergrapDuplicatehPadFoundError(FFmpegioError):
    ...
