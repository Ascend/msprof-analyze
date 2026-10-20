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
WITH MSTX_COMMUNICATION_DATA AS (
    SELECT
        ms.startNs AS mstxStartNs,
        ms.connectionId AS mstxConnectionId,
        replace(si.value, char(92) || '"', '"') AS value
    FROM
        MSTX_EVENTS ms
    JOIN
        STRING_IDS si
        ON ms.message = si.id
)
SELECT
    ta.startNs,
    ta.endNs,
    ta.connectionId,
    mstx.value
FROM
    MSTX_COMMUNICATION_DATA mstx
JOIN
    TASK ta
    ON mstx.mstxConnectionId = ta.connectionId
    OR (
        json_valid(mstx.value)
        AND CAST(json_extract(mstx.value, '$.streamId') AS INTEGER) = ta.streamId
    )
WHERE
    mstx.value LIKE '%"streamId":%'
    AND mstx.value LIKE '%"count":%'
    AND mstx.value LIKE '%"dataType":%'
    AND mstx.value LIKE '%"groupName":%'
    AND mstx.value LIKE '%"opName":%'
    AND mstx.mstxStartNs >= ? and mstx.mstxStartNs <= ?
    """


class Mstx2CommopExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
