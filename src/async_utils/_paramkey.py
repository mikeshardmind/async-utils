#   Copyright 2020-present Michael Hall
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

# This used to include CPython code, some minor performance losses have been
# taken to not tightly include upstream code


from __future__ import annotations

from collections.abc import Callable, Hashable

from . import _typings as t

__all__ = ("make_key",)


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


_marker: tuple[object] = (object(),)


def make_key(
    args: tuple[t.Any, ...],
    kwds: dict[t.Any, t.Any],
    _typ: Callable[[object], type] = type,
    _fast_types: set[type] = {int, str},  # noqa: B006
) -> Hashable:
    key: tuple[t.Any, ...] = args
    if kwds:
        key += _marker
        for item in kwds.items():
            key += item
    elif len(key) == 1 and _typ(key[0]) in _fast_types:
        return key[0]
    return _HK(key)
