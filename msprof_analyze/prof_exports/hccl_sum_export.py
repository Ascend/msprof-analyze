# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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

QUERY = """
SELECT
    NAME_IDS.value AS "OpName",
    TYPE_IDS.value AS "OpType",
    round(endNs - startNs) AS "Duration",
    GROUP_NAME_IDS.value AS "GroupName"
FROM
    COMMUNICATION_OP
LEFT JOIN
    STRING_IDS AS TYPE_IDS
    ON TYPE_IDS.id = COMMUNICATION_OP.opType
LEFT JOIN
    STRING_IDS AS NAME_IDS
    ON NAME_IDS.id = COMMUNICATION_OP.opName
LEFT JOIN
    STRING_IDS AS GROUP_NAME_IDS
    ON GROUP_NAME_IDS.id = COMMUNICATION_OP.groupName
WHERE COMMUNICATION_OP.startNs >= ? and COMMUNICATION_OP.startNs <= ?
    """


class HcclSumExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
