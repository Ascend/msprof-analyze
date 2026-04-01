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


QUERY_KERNEL_SHAPES = """
    WITH compute_info AS (
        SELECT 
            (SELECT value FROM STRING_IDS WHERE id = t.name) AS kernel_name,
            t.globalTaskId,
            (SELECT value FROM STRING_IDS WHERE id = t.opType) AS type,
            (SELECT value FROM STRING_IDS WHERE id = t.inputShapes) AS input_shapes,
            (SELECT value FROM STRING_IDS WHERE id = t.inputDataTypes) AS input_types,
            (SELECT value FROM STRING_IDS WHERE id = t.outputShapes) AS output_shapes
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

QUERY_OPERATOR_ARGS = """
    SELECT
        mstx.startNs,
        str_msg.value AS operator_args
    FROM
        MSTX_EVENTS mstx
    LEFT JOIN
        STRING_IDS str_msg ON mstx.message = str_msg.id
    LEFT JOIN
        STRING_IDS str_domain ON mstx.domainId = str_domain.id
    LEFT JOIN
        ENUM_MSTX_EVENT_TYPE mstx_type ON mstx_type.id = mstx.eventType
    WHERE
        mstx_type.name = 'marker' AND str_domain.value = ?
    ORDER BY mstx.startNs
"""


class KernelShapeExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_KERNEL_SHAPES

    def get_param_order(self):
        return []


class OperatorArgsExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_OPERATOR_ARGS

    def get_param_order(self):
        return ["op_args_domain"]
