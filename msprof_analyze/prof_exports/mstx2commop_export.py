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
    ta.startNs,
    ta.endNs,
    ta.connectionId,
    si.value
FROM
    MSTX_EVENTS ms
JOIN
    TASK ta
    ON ms.connectionId = ta.connectionId
JOIN
    STRING_IDS si
    ON ms.message = si.id
WHERE
    si.value LIKE '%"streamId":%'
    AND si.value LIKE '%"count":%'
    AND si.value LIKE '%"dataType":%'
    AND si.value LIKE '%"groupName":%'
    AND si.value LIKE '%"opName":%'
    AND ms.startNs >= ? and ms.startNs <= ?
    """


class Mstx2CommopExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]