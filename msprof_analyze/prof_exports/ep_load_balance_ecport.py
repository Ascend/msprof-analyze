# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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

GROUPED_MATMUL_QUERY = """
SELECT
    InputShapes_IDS.value AS "InputShapes"
FROM COMPUTE_TASK_INFO
JOIN TASK
    ON COMPUTE_TASK_INFO.globalTaskId = TASK.globalTaskId
LEFT JOIN STRING_IDS AS InputShapes_IDS
    ON InputShapes_IDS.id = COMPUTE_TASK_INFO.inputShapes
WHERE COMPUTE_TASK_INFO.opType = (
    SELECT id
    FROM STRING_IDS
    WHERE value = 'GroupedMatmul'
)
And TASK.startNs >= ? And TASK.endNs <= ?
    """


class InputShapeExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = GROUPED_MATMUL_QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
