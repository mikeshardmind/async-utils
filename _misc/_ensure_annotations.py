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

# Do NOT add `from __future__ import annotations` to this file.

import ast
import inspect
import sys
from types import FunctionType
from typing import Any

_cycle_blocked = False


#: PYUPDATE: py3.14, annotationslib based check as well.
#: TODO: This runs into issues with indentation, dedent source?
def ensure_annotations[T: type | FunctionType](f: T) -> T:
    """Ensure annotations are runtime valid.

    Returns
    -------
    A modified version of the object passed in
    without the annotations future in effect
    """
    # Prevents a cyclic compile issue
    global _cycle_blocked  # noqa: PLW0603
    if _cycle_blocked:
        return f

    new_ast = compile(
        ast.parse(inspect.getsource(f)),
        "<string>",
        "exec",
        flags=0,
        dont_inherit=True,
        optimize=1,
    )

    env = sys.modules[f.__module__].__dict__

    _cycle_blocked = True
    try:
        exec(new_ast, env)  # noqa: S102
    finally:
        _cycle_blocked = False

    return env[f.__name__]


def version_specific_annotation_interactions(obj: Any):
    if sys.version_info[:2] >= (3, 14):
        import annotationlib  # pyright: ignore[reportMissingImports]

        if isinstance(obj, type):
            for t in inspect.getmro(obj):
                for _name, static_obj in inspect.getmembers_static(t):
                    annotationlib.get_annotations(static_obj)  # pyright: ignore[reportUnknownMemberType]
        else:
            annotationlib.get_annotations(obj)  # pyright: ignore[reportUnknownMemberType]


if __name__ == "__main__":
    import importlib
    import pkgutil
    import sys

    import async_utils

    failures: list[tuple[str, Exception]] = []

    print("Checking annotations for runtime validity", flush=True)  # noqa: T201

    for mod_info in pkgutil.iter_modules(async_utils.__spec__.submodule_search_locations):
        mod = importlib.import_module(f"async_utils.{mod_info.name}")
        for name in getattr(mod, "__all__", ()):
            obj = getattr(mod, name)
            try:
                no_annot_fut_obj = ensure_annotations(obj)
                version_specific_annotation_interactions(no_annot_fut_obj)
            except TypeError:
                pass
            except (NameError, AttributeError) as exc:
                failures.append((f"{mod_info.name}.{name}", exc))

    if failures:
        for failing_obj, _exc in failures:
            exc_info = f"{_exc.__class__.__name__}: {_exc.args[0]}"
            print(failing_obj, exc_info, flush=True)  # noqa: T201

        sys.exit(1)
