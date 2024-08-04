from __future__ import annotations

from typing import Literal

PAD_INDEX = (
    tuple[int | None, int | None, int]
    | tuple[int | None, int | None]
    | tuple[int | None]
    | int
)
"""Filter pad index. 

- 3-element tuple = (chain, filter, pad)]
- 2-element tuple = (filter, pad)
- 1-element tuple = (pad,)
- int = pad

A None item indicates not specified and 
usually means to assign first available
"""

JOIN_HOW = Literal["chainable", "per_chain", "all", "auto"]
