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

"""LRU Implementation."""

from __future__ import annotations

__all__ = ("LRU",)


class LRU[K, V]:
    """An LRU implementation.

    Implements dict-like getitem/setitem access plus a couple methods.

    Parameters
    ----------
    maxsize: int
        The maximum number of items to retain
    """

    def __init__(self, maxsize: int, /) -> None:
        self._cache: dict[K, V] = {}
        self._maxsize = maxsize

    def get[T](self, key: K, default: T, /) -> V | T:
        """Get a value by key or default value.

        You should only use this when you have a default.
        Otherwise, use index into the LRU by key.

        Args:
            key: The key to lookup a value for
            default: A default value

        Returns
        -------
            Either the value associated to a key-value pair in the LRU
            or the specified default

        """
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: K, /) -> V:
        val = self._cache[key] = self._cache.pop(key)
        return val

    def __setitem__(self, key: K, value: V, /) -> None:
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.pop(next(iter(self._cache)))

    def remove(self, key: K, /) -> None:
        """Remove a key-value pair by key.

        It is not an error to attempt to remove a key which may not exist.

        Parameters
        ----------
        key:
            The key to remove.
        """
        self._cache.pop(key, None)
