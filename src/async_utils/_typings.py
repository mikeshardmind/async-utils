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

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Any, Final, Literal, Self, final
else:

    def final(f):  # noqa: ANN001
        return f


def __getattr__(name: str):
    if name == "final":  # this one actually executes at runtime
        return final

    if name in {"Any", "Final", "Literal", "Self"}:
        import typing

        return getattr(typing, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = ["Any", "Final", "Literal", "Self", "final"]
