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
