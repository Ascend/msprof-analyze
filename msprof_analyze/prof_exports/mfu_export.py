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

QUERY_MFU_FLOPS = """
    -- 查询 mfu_flops domain 下记录的算子 FLOPs range。
    SELECT
        mstx.startNs,
        mstx.endNs,
        str_msg.value as flops
    FROM
        MSTX_EVENTS mstx
    LEFT JOIN
        STRING_IDS str_msg ON mstx.message = str_msg.id
    LEFT JOIN
        STRING_IDS str_domain ON mstx.domainId = str_domain.id
    WHERE
        str_domain.value = 'mfu_flops'
    ORDER BY mstx.startNs
"""


class KernelShapeExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_KERNEL_SHAPES

    def get_param_order(self):
        return []


class MfuFlopsExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        """初始化 MFU FLOPs 查询。"""
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_MFU_FLOPS

    def get_param_order(self):
        """返回 SQL 查询参数顺序。"""
        return []
