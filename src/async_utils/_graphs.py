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

from collections.abc import Generator, Iterator

from . import _typings as t

TYPE_CHECKING = False
if TYPE_CHECKING:
    import typing

    class CanHashAndCompareLT(typing.Protocol):
        def __hash__(self) -> int: ...

        def __lt__(self, other: typing.Self, /) -> bool: ...

    class CanHashAndCompareGT(typing.Protocol):
        def __hash__(self) -> int: ...

        def __gt__(self, other: typing.Self, /) -> bool: ...

else:

    def f__hash__(self: t.Self) -> int: ...
    def f_binop_bool(self: t.Self, other: typing.Self, /) -> bool: ...

    class ExprWrapper:
        """Wrapper since call expressions aren't allowed in type statements."""

        def __class_getitem__(cls, key: int) -> t.Any:
            n = "__lt__" if key == 1 else "__gt__"
            data = {"__hash__": f__hash__, n: f_binop_bool}
            return type(
                "CoroCacheDeco",
                (__import__("typing").Protocol,),
                data,
            )

    type CanHashAndCompareLT = ExprWrapper[1]
    type CanHashAndCompareGT = ExprWrapper[2]


type CanHashAndCompare = CanHashAndCompareLT | CanHashAndCompareGT


class CycleDetected[T: CanHashAndCompare](Exception):
    @property
    def cycle(self) -> list[T]:
        return self.args[0]


class NodeData[T]:
    __slots__ = ("dependants", "ndependencies", "node")

    def __init__(self, node: T) -> None:
        self.node: T = node
        self.ndependencies: int = 0
        self.dependants: list[T] = []

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True


#: TODO: document the 3 uses I have for the below as examples
class DepSorter[T: CanHashAndCompare]:
    """Provides a topological sort that attempts to preserve logical priority
    (provided by comparison)

    If the set of nodes in a given graph has a strict total order
    via direct comparison (<), the resulting
    topological order for that graph is deterministic.

    Nodes may be added multiple times.
    Directed Edges are accumulated from all input information.
    """

    def __init_subclass__(cls) -> t.Never:
        msg = (
            "Don't subclass this. "
            "If you need anything more complex than this, "
            "pull a dedicated graph library."
        )
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, *edges: tuple[T, T]) -> None:
        self._nodemap: dict[T, NodeData[T]] = {}
        self.__iterating: bool = False

        for edge in edges:
            self.add_dependants(*edge)

    def add_dependencies(self, node: T, *dependencies: T) -> None:
        if self.__iterating:
            raise RuntimeError

        node_data = self._nodemap.setdefault(node, NodeData(node))

        for dep in dependencies:
            dep_node_data = self._nodemap.setdefault(dep, NodeData(dep))
            node_data.ndependencies += 1
            dep_node_data.dependants.append(node)

    def add_dependants(self, node: T, *dependants: T) -> None:
        if self.__iterating:
            raise RuntimeError

        node_data = self._nodemap.setdefault(node, NodeData(node))

        for dep in dependants:
            dep_node_data = self._nodemap.setdefault(dep, NodeData(dep))
            dep_node_data.ndependencies += 1
            node_data.dependants.append(dep)

    def _find_cycle(self) -> list[T] | None:
        graph = self._nodemap
        # Cheaper than a queue since we need to iterate anyhow
        queued: list[Iterator[T]] = []
        seen: set[T] = set()
        # Let's not recurse without TCO
        stack: list[T] = []
        node_depth: dict[T, int] = {}

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

    def __iter__(self) -> Generator[T, None, None]:
        if self.__iterating:
            raise RuntimeError

        self.__iterating = True

        if cycle := self._find_cycle():
            raise CycleDetected(cycle)

        return self.__iter()

    def __iter(self) -> Generator[T, None, None]:
        while ready := [
            i.node for i in self._nodemap.values() if not i.ndependencies
        ]:
            next_node = min(ready)
            self._nodemap[next_node].ndependencies = -1

            yield next_node

            for dep in self._nodemap[next_node].dependants:
                dep_info = self._nodemap[dep]
                dep_info.ndependencies -= 1
