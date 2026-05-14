# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import os
import sys
from functools import wraps
from typing import Dict, Any
from msprof_analyze.prof_common.logger import is_agent_mode

_json_output: Dict[str, Any] = {
    "status": "success",
    "code": 0,
    "message": {},
    "suggestion": "",
}


def set_json_success(msg_dict: Dict = None, suggestion: str = "") -> None:
    _json_output["status"] = "success"
    _json_output["code"] = 0
    _json_output["suggestion"] = suggestion
    if msg_dict is not None:
        _json_output["message"].update(msg_dict)


def set_json_error(code: int = 1, msg_dict: Dict = None, suggestion: str = "") -> None:
    _json_output["status"] = "error"
    _json_output["code"] = code
    _json_output["suggestion"] = suggestion
    if msg_dict is not None:
        _json_output["message"].update(msg_dict)


def get_json_output() -> Dict[str, Any]:
    output = dict(_json_output)
    log_path = os.environ.get("MSPROF_ANALYZE_LOG_FILE")
    if log_path:
        output["log_path"] = log_path
    return output


def write_json(data: Dict[str, Any]) -> None:
    if not is_agent_mode():
        return
    json_str = json.dumps(data, ensure_ascii=False) + "\n"
    sys.stdout.write(json_str)
    sys.stdout.flush()


def cli_json_output(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if result is not None and isinstance(result, dict):
                _json_output["message"].update(result)
            write_json(get_json_output())
            return 0
        except Exception as e:
            set_json_error(msg_dict={"err": str(e)})
            write_json(get_json_output())
            sys.exit(1)
    return wrapper
