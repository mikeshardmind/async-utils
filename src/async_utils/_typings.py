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

"""Shim for typing- and annotation-related symbols to avoid runtime dependencies on `typing` or `typing-extensions`.

A warning for annotation-related symbols: Do not directly import them from this module
(e.g. `from ._typings import Any`)! Doing so will trigger the module-level `__getattr__`, causing `typing` to
get imported. Instead, import the module and use symbols via attribute access as needed
(e.g. `from . import _typings [as t]`). To avoid those symbols being evaluated at runtime, which would also cause
`typing` to get imported, make sure to put `from __future__ import annotations` at the top of the module.
"""
# comment above
# taken nearly verbatim from quote from https://github.com/Sachaa-Thanasius in discord
# cause I forget otherwise too.

from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Concatenate, Literal, Never, Self
else:

    def __getattr__(name: str):
        if name in {"Any", "Concatenate", "Literal", "Never", "Self"}:
            import typing

            return getattr(typing, name)

        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)


__all__ = ("TYPE_CHECKING", "Any", "Concatenate", "Literal", "Never", "Self")
