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

from string import Template
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_common.constant import Constant


QUERY = Template("""
SELECT
    co.opName AS "$opNameId",
    siii.value AS "$opName",
    co.startNs AS "$startTime",
    co.endNs AS "$endTime",
    rdm.rankId AS "$globalRank",
    cti.srcRank AS "$srcRank",
    cti.dstRank AS "$dstRank",
    siiii.value AS "$taskType",
    sii.value AS "$coGroupName",
    si.value AS "$ctiGroupName"
FROM
    COMMUNICATION_TASK_INFO cti
    LEFT JOIN COMMUNICATION_OP co on cti.opId = co.opId
    CROSS JOIN RANK_DEVICE_MAP rdm
    JOIN STRING_IDS si on cti.groupName = si.id
    JOIN STRING_IDS sii on co.groupName = sii.id
    JOIN STRING_IDS siii on co.opName = siii.id
    JOIN STRING_IDS siiii on cti.taskType = siiii.id
    $condition
""")


class P2PPairingExport(BaseStatsExport):
    CO_OP_NAME = "opNameId"
    OP_NAME = "opName"
    START_TIME = "startTime"
    END_TIME = "endTime"
    GLOBAL_RANK = "globalRank"
    SRC_RANK = "srcRank"
    DST_RANK = "dstRank"
    TASK_TYPE = "taskType"
    CO_GROUP_NAME = "coGroupName"
    CTI_GROUP_NAME = "ctiGroupName"

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        filter_statement = """
            JOIN CANN_API ON CANN_API.connectionId = co.connectionId
            WHERE CANN_API.startNs >= ? and CANN_API.startNs <= ?
        """
        self._query = QUERY.safe_substitute(
            opNameId=self.CO_OP_NAME,
            opName=self.OP_NAME,
            startTime=self.START_TIME,
            endTime=self.END_TIME,
            globalRank=self.GLOBAL_RANK,
            srcRank=self.SRC_RANK,
            dstRank=self.DST_RANK,
            taskType=self.TASK_TYPE,
            coGroupName=self.CO_GROUP_NAME,
            ctiGroupName=self.CTI_GROUP_NAME,
            condition=filter_statement,
        )

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
