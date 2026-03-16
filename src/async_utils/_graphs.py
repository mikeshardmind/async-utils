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

import heapq
from collections.abc import Generator, Iterator

from . import _typings as t

TYPE_CHECKING = False
if TYPE_CHECKING:
    import typing
    from typing import Generic as Gen

    class CanHashAndCompareLT(typing.Protocol):
        def __hash__(self) -> int: ...

        def __lt__(self, other: typing.Any, /) -> bool: ...

    class CanHashAndCompareGT(typing.Protocol):
        def __hash__(self) -> int: ...

        def __gt__(self, other: typing.Any, /) -> bool: ...

    HashAndCompareT = typing.TypeVar("HashAndCompareT", bound="CanHashAndCompare")

else:

    class Gen:
        def __class_getitem__(*args: object) -> t.Any:
            return object

    class ExprWrapper:
        """Wrapper since call expressions aren't allowed in type statements."""

        def __class_getitem__(cls, key: int) -> t.Any:
            import typing

            if key == 1:

                class CanHashAndCompareLT(typing.Protocol):
                    def __hash__(self) -> int: ...

                    def __lt__(self, other: typing.Any, /) -> bool: ...

                return CanHashAndCompareLT

            class CanHashAndCompareGT(typing.Protocol):
                def __hash__(self) -> int: ...

                def __gt__(self, other: typing.Any, /) -> bool: ...

            return CanHashAndCompareGT

    type CanHashAndCompareLT = ExprWrapper[1]
    type CanHashAndCompareGT = ExprWrapper[2]

    HashAndCompareT = object


type CanHashAndCompare = CanHashAndCompareLT | CanHashAndCompareGT


class CycleDetected(Exception, Gen[HashAndCompareT]):
    if not TYPE_CHECKING:

        def __class_getitem__(cls, *_dont_care: object) -> type:
            return cls

    @property
    def cycle(self) -> list[HashAndCompareT]:
        return self.args[0]


class NodeData(Gen[HashAndCompareT]):
    if not TYPE_CHECKING:

        def __class_getitem__(cls, *_dont_care: object) -> type:
            return cls

    __slots__ = ("dependants", "ndependencies", "node")

    def __init__(self, node: HashAndCompareT) -> None:
        self.node: HashAndCompareT = node
        self.ndependencies: int = 0
        self.dependants: list[HashAndCompareT] = []

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    def __lt__(self, other: t.Self) -> bool:  # falback for tuple sorting
        return True

    __final__ = True


#: TODO: document the 3 uses I have for the below as examples
class DepSorter(Gen[HashAndCompareT]):
    """Provides a topological sort that attempts to preserve logical priority
    (provided by comparison)

    If the set of nodes in a given graph has a strict total order
    via direct comparison (<), the resulting
    topological order for that graph is deterministic.

    Nodes may be added multiple times.
    Directed Edges are accumulated from all input information.
    """

    if not TYPE_CHECKING:

        def __class_getitem__(cls, *_dont_care: object) -> type:
            return cls

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this."
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, *edges: tuple[HashAndCompareT, HashAndCompareT]) -> None:
        self._nodemap: dict[HashAndCompareT, NodeData[HashAndCompareT]] = {}
        self.__iterating: bool = False

        for edge in edges:
            self.add_dependants(*edge)

    def add_dependencies(self, node: HashAndCompareT, *dependencies: HashAndCompareT) -> None:
        if self.__iterating:
            raise RuntimeError

        node_data = self._nodemap.setdefault(node, NodeData(node))

        for dep in dependencies:
            dep_node_data = self._nodemap.setdefault(dep, NodeData(dep))
            node_data.ndependencies += 1
            dep_node_data.dependants.append(node)

    def add_dependants(self, node: HashAndCompareT, *dependants: HashAndCompareT) -> None:
        if self.__iterating:
            raise RuntimeError

        node_data = self._nodemap.setdefault(node, NodeData(node))

        for dep in dependants:
            dep_node_data = self._nodemap.setdefault(dep, NodeData(dep))
            dep_node_data.ndependencies += 1
            node_data.dependants.append(dep)

    def _find_cycle(self) -> list[HashAndCompareT] | None:
        graph = self._nodemap
        # Cheaper than a queue since we need to iterate anyhow
        queued: list[Iterator[HashAndCompareT]] = []
        seen: set[HashAndCompareT] = set()
        # Let's not recurse without TCO
        stack: list[HashAndCompareT] = []
        node_depth: dict[HashAndCompareT, int] = {}

        # without this, mypy doesn't check total consistent use
        # and instead binds to just HashAndCompareT due to iterating graph
        node: HashAndCompareT | None

        for node in graph:
            if node in seen:
                continue

            while True:
                if node in seen:
                    if node in node_depth:
                        return [*stack[node_depth[node] :], node]
                else:
                    seen.add(node)
                    iterator = iter(graph[node].dependants)
                    queued.append(iterator)
                    node_depth[node] = len(stack)
                    stack.append(node)

                while stack:
                    if (node := next(queued[-1], None)) is not None:
                        break
                    del node_depth[stack.pop()]
                    queued.pop()
                else:
                    break
        return None

    def __iter__(self) -> Generator[HashAndCompareT, None, None]:
        if self.__iterating:
            raise RuntimeError

        self.__iterating = True

        if cycle := self._find_cycle():
            raise CycleDetected(cycle)

        return self.__iter()

    def __iter(self) -> Generator[HashAndCompareT, None, None]:
        m = self._nodemap
        ready = [(n, i) for n, i in m.items() if not i.ndependencies]
        heapq.heapify(ready)
        while ready:
            next_node, info = heapq.heappop(ready)
            info.ndependencies = -1

            yield next_node

            for dep in info.dependants:
                dep_info = self._nodemap[dep]
                dep_info.ndependencies -= 1
                if not dep_info.ndependencies:
                    heapq.heappush(ready, (dep, dep_info))
