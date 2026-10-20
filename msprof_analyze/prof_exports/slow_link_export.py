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

QUERY = """
    SELECT
        si.value AS groupName,
        co.endNs - co.startNs AS communicationTime,
        sii.value AS opName,
        op.value AS opType,
        et.name AS dataType,
        CASE
    WHEN et.name = 'INT8' THEN 1 * co.count
        WHEN et.name = 'INT16' THEN 2 * co.count
        WHEN et.name = 'INT32' THEN 4 * co.count
        WHEN et.name = 'INT64' THEN 8 * co.count
        WHEN et.name = 'UINT64' THEN 8 * co.count
        WHEN et.name = 'UINT8' THEN 1 * co.count
        WHEN et.name = 'UINT16' THEN 2 * co.count
        WHEN et.name = 'UINT32' THEN 4 * co.count
        WHEN et.name = 'FP16' THEN 2 * co.count
        WHEN et.name = 'FP32' THEN 4 * co.count
        WHEN et.name = 'FP64' THEN 8 * co.count
        WHEN et.name = 'BFP16' THEN 2 * co.count
        WHEN et.name = 'INT128' THEN 16 * co.count
        END AS dataSize
    FROM
        COMMUNICATION_OP co
    CROSS
        JOIN STRING_IDS si ON co.groupName = si.id
        JOIN STRING_IDS sii ON co.opName = sii.id
        JOIN ENUM_HCCL_DATA_TYPE et ON co.dataType = et.id
        JOIN STRING_IDS op ON co.opType = op.id
"""


class SlowLinkExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, {})
        self._query = QUERY

    def get_param_order(self):
        return []
