"""A Collection of async and other concurrency utilities.

:copyright: (c) 2020-present Michael Hall
:license: Apache License, Version 2.0, see LICENSE for more details.

"""

__title__ = "async_utils"
__author__ = "Michael Hall"
__license__ = "Apache-2.0"
__copyright__ = "Copyright 2020-Present Michael Hall"
__version__ = "2024.12.13"

import os
import sys

vi = sys.version_info
if (vi.major, vi.minor) > (3, 13):
    msg = """This library is not tested for use on python versions above 3.13
    This library relies on a few internal details that are not safe to rely upon
    without checking this consistently.
    """
    if os.getenv("ASYNC_UTILS_UNCHECKED_PY_VER", ""):
        import logging

        logging.getLogger(__file__).warning(msg)
    else:
        raise RuntimeError(msg)
