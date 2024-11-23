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
    """This class guarantees that hash() will be called no more than once
    per element.  This is important because the lru_cache() will hash
    the key multiple times on a cache miss."""

    __slots__ = ("hashvalue",)

    def __init__(
        self,
        tup: tuple[Any, ...],
        hash: Callable[[object], int] = hash,  # noqa: A002
    ):
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
    """Make a cache key from optionally typed positional and keyword arguments
    The key is constructed in a way that is flat as possible rather than
    as a nested structure that would take more memory.
    If there is only a single argument and its data type is known to cache
    its hash value, then that argument is returned without a wrapper.  This
    saves space and improves lookup speed."""
    # All of code below relies on kwds preserving the order input by the user.
    # Formerly, we sorted() the kwds before looping.  The new way is *much*
    # faster; however, it means that f(x=1, y=2) will now be treated as a
    # distinct call from f(y=2, x=1) which will be cached separately.
    key: tuple[Any, ...] = args
    if kwds:
        key += kwd_mark
        for item in kwds.items():
            key += item
    elif len(key) == 1 and type(key[0]) in fasttypes:
        return key[0]
    return _HashedSeq(key)
