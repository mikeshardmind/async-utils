# code below is modified from: https://github.com/python/cpython/blob/3.11/Lib/functools.py#L448-L477

# Which was originally:
# # Written by Nick Coghlan <ncoghlan at gmail.com>,
# Raymond Hettinger <python at rcn.com>,
# and Łukasz Langa <lukasz at langa.pl>.
#   Copyright (C) 2006-2013 Python Software Foundation.

# The license in it's original form may be found: https://github.com/python/cpython/blob/3.11/LICENSE
# And is also included in this repository as ``LICENSE_cpython``

# It's included in minimal, simplified form based on specific use


from __future__ import annotations

from collections.abc import Callable, Hashable, Sized
from typing import Any


class _HashedSeq(list[Any]):
    __slots__ = ("hashvalue",)

    def __init__(
        self,
        tup: tuple[Any, ...],
        hash: Callable[[object], int] = hash,  # noqa: A002
    ) -> None:
        self[:] = tup
        self.hashvalue: int = hash(tup)

    def __hash__(self) -> int:  # pyright: ignore[reportIncompatibleVariableOverride]
        return self.hashvalue


def make_key(
    args: tuple[Any, ...],
    kwds: dict[Any, Any],
    kwd_mark: tuple[object] = (object(),),
    fasttypes: set[type] = {int, str},  # noqa: B006
    type: type[type] = type,  # noqa: A002
    len: Callable[[Sized], int] = len,  # noqa: A002
) -> Hashable:
    key: tuple[Any, ...] = args
    if kwds:
        key += kwd_mark
        for item in kwds.items():
            key += item
    elif len(key) == 1 and type(key[0]) in fasttypes:
        return key[0]
    return _HashedSeq(key)
