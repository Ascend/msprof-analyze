# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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


QUERY_KERNEL_BYTES = """
    WITH compute_info AS (
        SELECT
            (SELECT value FROM STRING_IDS WHERE id = t.name) AS kernel_name,
            t.globalTaskId,
            (SELECT value FROM STRING_IDS WHERE id = t.opType) AS type,
            (SELECT value FROM STRING_IDS WHERE id = t.inputShapes) AS input_shapes,
            (SELECT value FROM STRING_IDS WHERE id = t.inputDataTypes) AS input_types,
            (SELECT value FROM STRING_IDS WHERE id = t.outputShapes) AS output_shapes,
            (SELECT value FROM STRING_IDS WHERE id = t.outputDataTypes) AS output_types
        FROM
            COMPUTE_TASK_INFO t
    )
    SELECT
        compute_info.*,
        task.startNs as kernel_ts,
        task.endNs as kernel_end,
        task.endNs - task.startNs as task_duration
    FROM
        compute_info
    JOIN
        TASK as task ON compute_info.globalTaskId = task.globalTaskId
    ORDER BY task.startNs;
"""


class KernelBytesExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_KERNEL_BYTES

    def get_param_order(self):
        return []
