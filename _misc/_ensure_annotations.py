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

_cycle_blocked = False


#: PYUPDATE: py3.14, annotationslib based check as well.
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
