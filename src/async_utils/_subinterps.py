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

import time
import concurrent.futures as cf
import marshal
import sys
import types


match sys.version_info[:2]:
    case (3, 13) | (3, 14):
        import _interpreters as sints
        import _interpchannels as schans
    case (3, 12):
        import _xxsubinterpreters as sints
        import _xxinterpchannel as schans
    case _ as x:
        msg = f"Subinterpreter support not available for python version {x}"
        raise RuntimeError(msg)


# TODO: consider better options than the channel pair

def do_loop(code_obj: bytes, recv_channel_id: schans.ChannelID, send_channel_id: schans.ChannelID):
    f = marshal.loads(code_obj)
    while True:
        action, value = schans.recv(recv_channel_id, (None, None))
        if action is None:
            time.sleep(sys.getswitchinterval())
            continue

        if action == "shutdown":
            break

        if action == "submit":
            v = f(marshal.loads(value))
            schans.send(send_channel_id, marshal.dumps(v))


class SubinterpreterWorker:
    def __init__(self, function: types.FunctionType | types.BuiltinFunctionType):
        ...