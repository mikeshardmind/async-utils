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

"""LRU Implementations."""

from __future__ import annotations

import heapq
import time

__all__ = ("LRU", "TTLLRU")


class LRU[K, V]:
    """An LRU implementation.

    Implements dict-like getitem/setitem access plus a couple methods.

    While the internal structure is threadsafe,
    concurrent access and modification of it is not.
    Use a threading lock to synchronize access if needed.

    This is not locked automatically to avoid paying the cost
    in applications that do not share this across threads.

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

        Parameters
        ----------
        key:
            The key to lookup a value for
        default:
            A default value

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


class TTLLRU[K, V]:
    """An LRU implementation with a ttl.

    While the internal structure is threadsafe,
    concurrent access and modification of it is not.
    Use a threading lock to synchronize access if needed.

    This is not locked automatically to avoid paying the cost
    in applications that do not share this across threads.

    Key/value references and gc:
        Keys are kept alive in a heap ordered by expiration,
        with each access and modification removing up to one expired key
        This may keep keys alive longer than an eager eviction
        would.

        Upon retrieving values, if they are considered expired, they
        are removed and not returned.

        This keeps the per operation performance predictable.

        This does mean that it is possible to have up to the maxsize
        in keys that are persistently alive if the cache ceases to be accessed
        but is kept alive.

    Parameters
    ----------
    maxsize: int
        The maximum number of items to retain
    ttl: float
        The number of seconds to retain validity of items for.
        Items are not eagerly evicted at expiration.
        Getting items does not refresh their ttl.
    """

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._cache: dict[K, tuple[float, V]] = {}
        self._maxsize: int = maxsize
        self._ttl: float = ttl
        self._expirations: list[tuple[float, K]] = []

    def _remove_one_expired(self) -> None:
        """Remove up to one expired entry."""
        now = time.monotonic()
        while self._expirations:
            ts, k = heapq.heappop(self._expirations)
            if ts < now:
                try:
                    ts, _v = self._cache[k]
                except KeyError:
                    continue
                if ts < now:
                    self._cache.pop(k, None)
                    return
            else:
                heapq.heappush(self._expirations, (ts, k))
                break

    def __getitem__(self, key: K, /) -> V:
        self._remove_one_expired()
        ts, val = self._cache[key] = self._cache.pop(key)
        now = time.monotonic()
        if now > ts:
            raise KeyError
        self._cache[key] = ts, val
        return val

    def __setitem__(self, key: K, value: V, /) -> None:
        ts = time.monotonic() + self._ttl
        heapq.heappush(self._expirations, (ts, key))
        self._cache[key] = (ts, value)
        self._remove_one_expired()
        if len(self._cache) > self._maxsize:
            self._cache.pop(next(iter(self._cache)))

    def get[T](self, key: K, default: T, /) -> V | T:
        """Get a value by key or default value.

        You should only use this when you have a default.
        Otherwise, use index into the LRU by key.

        Parameters
        ----------
        key:
            The key to lookup a value for
        default:
            A default value

        Returns
        -------
            Either the value associated to a key-value pair in the LRU
            or the specified default

        """
        try:
            return self[key]
        except KeyError:
            return default

    def remove(self, key: K, /) -> None:
        """Remove a key-value pair by key.

        It is not an error to attempt to remove a key which may not exist.

        Parameters
        ----------
        key:
            The key to remove.
        """
        self._remove_one_expired()
        self._cache.pop(key, None)
