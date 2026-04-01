# Copyright (c) 2024, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
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

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_common.constant import Constant

QUERY = """
SELECT
    NAME_IDS.value AS "OpName",
    OPTYPE_IDS.value AS "OpType",
    TASKTYPE_IDS.value AS "TaskType",
    INPUTSHAPES_IDS.value AS "InputShapes",
    round(TASK.endNs - TASK.startNs) AS "Duration"
FROM
    COMPUTE_TASK_INFO
LEFT JOIN TASK
    ON TASK.globalTaskId = COMPUTE_TASK_INFO.globalTaskId
LEFT JOIN
    STRING_IDS AS NAME_IDS
    ON NAME_IDS.id = COMPUTE_TASK_INFO.name
LEFT JOIN
    STRING_IDS AS OPTYPE_IDS
    ON OPTYPE_IDS.id = COMPUTE_TASK_INFO.opType
LEFT JOIN
    STRING_IDS AS TASKTYPE_IDS
    ON TASKTYPE_IDS.id = COMPUTE_TASK_INFO.taskType
LEFT JOIN
    STRING_IDS AS INPUTSHAPES_IDS
    ON INPUTSHAPES_IDS.id = COMPUTE_TASK_INFO.inputShapes
WHERE TASK.startNs >= ? and TASK.startNs <= ?
    """

QUERY_EXCLUDE_OPNAME = """
SELECT
    OPTYPE_IDS.value AS "OpType",
    TASKTYPE_IDS.value AS "TaskType",
    INPUTSHAPES_IDS.value AS "InputShapes",
    round(TASK.endNs - TASK.startNs) AS "Duration"
FROM
    COMPUTE_TASK_INFO
LEFT JOIN TASK
    ON TASK.globalTaskId = COMPUTE_TASK_INFO.globalTaskId
LEFT JOIN
    STRING_IDS AS OPTYPE_IDS
    ON OPTYPE_IDS.id = COMPUTE_TASK_INFO.opType
LEFT JOIN
    STRING_IDS AS TASKTYPE_IDS
    ON TASKTYPE_IDS.id = COMPUTE_TASK_INFO.taskType
LEFT JOIN
    STRING_IDS AS INPUTSHAPES_IDS
    ON INPUTSHAPES_IDS.id = COMPUTE_TASK_INFO.inputShapes
WHERE TASK.startNs >= ? and TASK.startNs <= ?
"""


class ComputeOpSumExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


class ComputeOpSumExportExcludeOpName(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_EXCLUDE_OPNAME

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
