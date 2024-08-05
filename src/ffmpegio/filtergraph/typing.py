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

PAD_PAIR = (
    tuple[PAD_INDEX, PAD_INDEX]
    | tuple[PAD_INDEX | list[PAD_INDEX], None]
    | tuple[None, PAD_INDEX]
)
"""Specifies a filter pad linkage or labeling

A tuple pair of input pad and output pad. 

- Set input or output pad is ``None`` to define a pad label
- If input label is an input stream specifier (e.g., 0:v or 1:a:0) and connects
  to multiple filter inputs, specify with a list the input pad indices.

"""

JOIN_HOW = Literal["chainable", "per_chain", "all", "auto"]
