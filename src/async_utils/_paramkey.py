# This used to include CPython code, some minor performance losses have been
# taken to not tightly include upstream code


from __future__ import annotations

from collections.abc import Hashable
from typing import Any, Final, final


@final
class _HK:
    __slots__ = ("_hashvalue", "_tup")

    def __init__(self, tup: Hashable) -> None:
        self._tup = tup
        self._hashvalue = hash(tup)

    def __hash__(self) -> int:
        return self._hashvalue

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _HK):
            return False
        return self._tup == other._tup


_marker: Final[tuple[object]] = (object(),)


def make_key(args: tuple[Any, ...], kwds: dict[Any, Any]) -> Hashable:
    key: tuple[Any, ...] = args
    if kwds:
        key += _marker
        for item in kwds.items():
            key += item
    elif len(key) == 1 and type(key[0]) in {int, str}:
        return key[0]
    return _HK(key)
