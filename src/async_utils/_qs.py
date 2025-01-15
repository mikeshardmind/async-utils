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

# With thanks to everyone I've ever discussed concurrency or datastructures with

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Generator
from heapq import heappop, heappush

from . import _typings as t

__all__ = ("LIFOQueue", "PriorityQueue", "Queue", "QueueEmpty", "QueueFull")


class QueueEmpty(Exception):
    pass


class QueueFull(Exception):
    pass


class AsyncEvent:
    __slots__ = ("_cancelled", "_future", "_loop", "_unset")

    def __init__(self, /) -> None:
        self._loop = asyncio.get_running_loop()
        self._future = None
        self._unset = [True]
        self._cancelled = False

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __reduce__(self, /) -> t.Never:
        raise TypeError

    def __bool__(self, /) -> bool:
        return not self._unset

    def cancel(self, /) -> bool:
        cancelled = self._cancelled

        if not cancelled and (unset := self._unset):
            try:
                unset.pop()
            except IndexError:
                pass
            else:
                self._cancelled = cancelled = True

        return cancelled

    def is_set(self, /):
        return not self._unset

    def is_cancelled(self, /):
        return self._cancelled

    def __await__(self, /) -> Generator[t.Any, t.Any, bool]:
        if self._unset:
            self._future = self._loop.create_future()

            try:
                yield from self._future.__await__()
            except BaseException:
                self.cancel()
                raise
            finally:
                self._future = None
        else:
            yield from asyncio.sleep(0).__await__()

        return True

    def _set_state(self, /):
        if (future := self._future) is not None:
            try:  # faster to race than lock
                future.set_result(True)
            except asyncio.InvalidStateError:
                pass

    def set_state(self, /):
        success = True

        if is_unset := self._unset:
            try:
                is_unset.pop()
            except IndexError:
                success = False
            else:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is self._loop:
                    self._set_state()
                else:
                    try:
                        self._loop.call_soon_threadsafe(self._set_state)
                    except RuntimeError:
                        pass
        else:
            success = False

        return success


class ThreadingEvent:
    __slots__ = ("_cancelled", "_lock", "_unset")

    def __init__(self, /) -> None:
        self._unset = [True]
        self._cancelled = False
        self._lock = threading.Lock()
        self._lock.acquire()

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __reduce__(self, /) -> t.Never:
        raise TypeError

    def wait(self, /, timeout: float | None = None) -> bool:
        if not self._unset:
            return True

        if timeout is None:
            return self._lock.acquire()
        if timeout > 0:
            return self._lock.acquire(timeout=timeout)

        return self._lock.acquire(blocking=False)

    def __bool__(self, /) -> bool:
        return not self._unset

    def cancel(self, /) -> bool:
        cancelled = self._cancelled

        if not cancelled and (unset := self._unset):
            try:
                unset.pop()
            except IndexError:
                pass
            else:
                self._cancelled = cancelled = True

        return cancelled

    def is_set(self, /) -> bool:
        return not self._unset

    def is_cancelled(self, /) -> bool:
        return self._cancelled

    def set_state(self, /) -> bool:
        success = True

        if is_unset := self._unset:
            try:
                is_unset.pop()
            except IndexError:
                success = False
            else:
                self._lock.release()
        else:
            success = False

        return success


class Semaphore:
    __slots__ = (
        "__weakref__",
        "_unlocked",
        "_value",
        "_waiters",
    )

    def __init__(self, value: int = 1, /) -> None:
        self._value: int = value
        self._waiters: deque[AsyncEvent | ThreadingEvent] = deque()
        self._unlocked: list[None] = [None] * self._value

    async def __aenter__(self, /) -> t.Self:
        await self.async_acquire()
        return self

    async def __aexit__(self, *dont_care: object) -> None:
        self.release()

    def __enter__(self, /) -> t.Self:
        self.sync_acquire()

        return self

    def __exit__(self, *dont_care: object) -> None:
        self.release()

    def _acquire_nowait(self, /) -> bool:
        if unlocked := self._unlocked:
            try:
                unlocked.pop()
            except IndexError:
                success = False
            else:
                success = True
        else:
            success = False

        return success

    async def async_acquire(self) -> bool:
        waiters = self._waiters
        success = self._acquire_nowait()
        rescheduled = False

        if not success:
            waiters.append(event := AsyncEvent())

            try:
                success = self._acquire_nowait()

                if not success:
                    success = await event
                    rescheduled = True
            finally:
                if success or event.cancel():
                    try:
                        waiters.remove(event)
                    except ValueError:
                        pass
                else:
                    self.release()

        if not rescheduled:
            await asyncio.sleep(0)

        return success

    def sync_acquire(
        self, /, *, blocking: bool = True, timeout: float | None = None
    ) -> bool:
        waiters = self._waiters
        success = self._acquire_nowait()

        if success := self._acquire_nowait():
            return True

        if not blocking:
            return False

        waiters.append(event := ThreadingEvent())

        try:
            success = self._acquire_nowait()

            if not success:
                success = event.wait(timeout)
        finally:
            if success or event.cancel():
                try:
                    waiters.remove(event)
                except ValueError:
                    pass
            else:
                self.release()

        return success

    def release(self) -> None:
        waiters = self._waiters
        unlocked = self._unlocked
        count = 1

        while True:
            if waiters:
                if not count:
                    if self._acquire_nowait():
                        count = 1
                    else:
                        break

                try:
                    event = waiters[0]
                except IndexError:
                    pass
                else:
                    if event.is_set():
                        count -= 1

                    try:
                        waiters.remove(event)
                    except ValueError:
                        pass

                    if count or unlocked:
                        continue
                    break

            if count == 1:
                unlocked.append(None)
            elif count > 1:
                unlocked.extend([None] * count)
            else:
                break

            if waiters:
                count = 0
            else:
                break

    @property
    def waiting(self, /) -> int:
        return len(self._waiters)

    @property
    def value(self, /) -> int:
        return len(self._unlocked)


class _BaseQueue[T]:
    __slots__ = (
        "__get_waiters",
        "__put_waiters",
        "__unlocked",
        "__waiters",
        "_data",
        "maxsize",
    )

    def __init__(self, /, maxsize: int | None = None) -> None:
        self.__waiters: deque[AsyncEvent | ThreadingEvent] = deque()
        self.__get_waiters: deque[AsyncEvent | ThreadingEvent] = deque()
        self.__put_waiters: deque[AsyncEvent | ThreadingEvent] = deque()
        self.__unlocked: list[bool] = [True]
        self.maxsize: int = maxsize if maxsize is not None else 0

    def __bool__(self, /) -> bool:
        return self._qsize() > 0

    def __len__(self, /) -> int:
        return self._qsize()

    def _acquire_nowait(self, /) -> bool:
        if unlocked := self.__unlocked:
            try:
                unlocked.pop()
            except IndexError:
                success = False
            else:
                success = True
        else:
            success = False

        return success

    def _acquire_nowait_put(self, /) -> bool:
        maxsize = self.maxsize

        if unlocked := self.__unlocked:
            if maxsize <= 0:
                try:
                    unlocked.pop()
                except IndexError:
                    success = False
                else:
                    success = True
            elif self._qsize() < maxsize:
                try:
                    unlocked.pop()
                except IndexError:
                    success = False
                else:
                    if self._qsize() < maxsize:
                        success = True
                    else:
                        self._release()

                        success = False
            else:
                success = False
        else:
            success = False

        return success

    def _acquire_nowait_get(self, /):
        if unlocked := self.__unlocked:
            if self._qsize() > 0:
                try:
                    unlocked.pop()
                except IndexError:
                    success = False
                else:
                    if self._qsize() > 0:
                        success = True
                    else:
                        self._release()

                        success = False
            else:
                success = False
        else:
            success = False

        return success

    def _release(self, /):
        maxsize = self.maxsize

        unlocked = self.__unlocked

        while True:
            size = self._qsize()

            if not size:
                actual_waiters = self.__put_waiters
            elif size >= maxsize > 0:
                actual_waiters = self.__get_waiters
            else:
                actual_waiters = self.__waiters

            while actual_waiters:
                try:
                    event = actual_waiters.popleft()
                except IndexError:
                    pass
                else:
                    if event.set_state():
                        break
            else:
                unlocked.append(True)

                if actual_waiters and self._acquire_nowait():
                    continue

            break

    async def async_put(self, /, item: T, *, blocking: bool = True):
        waiters = self.__waiters
        put_waiters = self.__put_waiters
        success = self._acquire_nowait_put()

        try:
            if not success:
                event = AsyncEvent()
                waiters.append(event)
                put_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_put()):
                        success = await event
                finally:
                    if success or event.cancel():
                        try:
                            put_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueFull

            self._put(item)
        finally:
            if success:
                self._release()

    def sync_put(
        self, /, item: T, *, blocking: bool = True, timeout: float | None = None
    ):
        waiters = self.__waiters
        put_waiters = self.__put_waiters
        success = self._acquire_nowait_put()

        try:
            if not success:
                if not blocking:
                    raise QueueFull

                event = ThreadingEvent()
                waiters.append(event)
                put_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_put()):
                        success = event.wait(timeout)
                finally:
                    if success or event.cancel():
                        try:
                            put_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueFull

            self._put(item)
        finally:
            if success:
                self._release()

    async def async_get(self, /) -> T:
        waiters = self.__waiters
        get_waiters = self.__get_waiters
        success = self._acquire_nowait_get()

        try:
            if not success:
                event = AsyncEvent()
                waiters.append(event)
                get_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_get()):
                        success = await event
                finally:
                    if success or event.cancel():
                        try:
                            get_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueEmpty

            item = self._get()
        finally:
            if success:
                self._release()

        return item

    def threading_get(
        self, /, *, blocking: bool = True, timeout: float | None = None
    ) -> T:
        waiters = self.__waiters
        get_waiters = self.__get_waiters

        success = self._acquire_nowait_get()

        try:
            if not success:
                if not blocking:
                    raise QueueFull

                event = ThreadingEvent()
                waiters.append(event)
                get_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_get()):
                        success = event.wait(timeout)
                finally:
                    if success or event.cancel():
                        try:
                            get_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueEmpty

            item = self._get()
        finally:
            if success:
                self._release()

        return item

    def _qsize(self, /) -> int:
        raise NotImplementedError

    def _items(self, /) -> list[T]:
        raise NotImplementedError

    def _put(self, /, item: T) -> None:
        raise NotImplementedError

    def _get(self, /) -> T:
        raise NotImplementedError

    @property
    def waiting(self, /):
        return len(self.__waiters)

    @property
    def putting(self, /):
        return len(self.__put_waiters)

    @property
    def getting(self, /):
        return len(self.__get_waiters)


class Queue[T](_BaseQueue[T]):
    __slots__ = ("_data",)

    def __init__(self, /, maxsize: int | None = None) -> None:
        super().__init__(maxsize)
        self._data: deque[T] = deque()

    def _qsize(self, /):
        return len(self._data)

    def _items(self, /):
        return list(self._data)

    def _put(self, /, item: T):
        self._data.append(item)

    def _get(self, /):
        return self._data.popleft()


class LIFOQueue[T](Queue[T]):
    def _get(self, /):
        return self._data.pop()


class PriorityQueue[T](_BaseQueue[T]):
    __slots__ = ("_data",)

    def __init__(self, /, maxsize: int | None = None) -> None:
        super().__init__(maxsize)
        self._data: list[T] = []

    def _qsize(self, /) -> int:
        return len(self._data)

    def _items(self, /) -> list[T]:
        return self._data.copy()

    def _put(self, /, item: T):
        heappush(self._data, item)

    def _get(self, /) -> T:
        return heappop(self._data)
