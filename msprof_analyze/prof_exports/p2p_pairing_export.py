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
            condition=filter_statement
        )

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
