# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
