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

__all__ = ("LRU",)


class LRU[K, V]:
    def __init__(self, maxsize: int, /):
        self.cache: dict[K, V] = {}
        self.maxsize = maxsize

    def get[T](self, key: K, default: T, /) -> V | T:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: K, /) -> V:
        val = self.cache[key] = self.cache.pop(key)
        return val

    def __setitem__(self, key: K, value: V, /):
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.pop(next(iter(self.cache)))

    def remove(self, key: K, /) -> None:
        self.cache.pop(key, None)
