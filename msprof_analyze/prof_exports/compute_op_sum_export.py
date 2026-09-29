# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

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
