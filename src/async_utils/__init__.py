"""A Collection of async and other concurrency utilities.

:copyright: (c) 2020-present Michael Hall
:license: Apache License, Version 2.0, see LICENSE for more details.

"""

__title__ = "async_utils"
__author__ = "Michael Hall"
__license__ = "Apache-2.0"
__copyright__ = "Copyright 2020-Present Michael Hall"
__version__ = "2025.03.08b"

import os
import sys

_vi = sys.version_info

# - Check use of concurrent.futures.Future before extending this version.
# - update `_misc._ensure_annotations.py` before extending this version.
# - ensure `task_cache.__WrappedSignature` still works
if (_vi.major, _vi.minor) > (3, 13):
    msg: str = """This library is not tested for use on python versions above 3.13
    This library relies on a few internal details that are not safe to rely upon
    without checking this consistently.
    """
    if os.getenv("ASYNC_UTILS_UNCHECKED_PY_VER", ""):
        import logging

        msg += """\n\nThis is not neccessarily broken, but if you encounter an
        issue with it, please be aware that the library has not actively
        chosen to support the python version you have opted into using this on
        *yet*. If you encounter an issue with it, please do still report it.
        """

        logging.getLogger(__name__).warning(msg)
    elif sys.version_info.releaselevel in {"alpha", "beta", "candidate"}:
        import logging

        msg += """\nThanks for testing this (and a development version of python)
        prior to release!.\n"""
        logging.getLogger(__name__).warning(msg)
    else:
        msg += """\nYou can change this error to a warning if you are sure it is
        safe and are willing to take the risk on yourself before I have verified
        it by setting the environment variable `ASYNC_UTILS_UNCHECKED_PY_VER`
        to a non-empty value.
        """
        raise RuntimeError(msg)
