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


from __future__ import annotations

import asyncio
from collections.abc import Hashable
from typing import Generic, TypeVar
from weakref import WeakValueDictionary

__all__ = ["KeyedLocks"]

KT = TypeVar("KT", bound=Hashable)


class KeyedLocks(Generic[KT]):
    """Locks per hashable resource type
    Currently implemented with a weakvalue dictionary + asyncio.Locks
    implementation could be improved to not rely on weakreference in the future
    for performance reasons, but this would likely involve also re-implementing
    some of the functionality of asyncio locks. May revisit later, intent here
    is that if I do, everything I use like this improves at once.
    """

    def __init__(self) -> None:
        self._locks: WeakValueDictionary[KT, asyncio.Lock] = WeakValueDictionary()

    def __getitem__(self, item: KT) -> asyncio.Lock:
        return self._locks.get(item, self._locks.setdefault(item, asyncio.Lock()))
