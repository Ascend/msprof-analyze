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
WITH
    summary as (
        SELECT
            name,
            sum(endNs - startNs) AS duration,
            count (*) AS num,
            avg(endNs - startNs) AS avg_duration,
            min(endNs - startNs) AS min_duration,
            median(endNs - startNs) AS med_duration,
            max(endNs - startNs) AS max_duration,
            stdev(endNs - startNs) AS stdev_duration,
            lower_quartile(endNs - startNs) AS lower_quartile_duration,
            upper_quartile(endNs - startNs) AS upper_quartile_duration
        FROM
            CANN_API
        WHERE CANN_API.startNs >= ? and CANN_API.startNs <= ?
        GROUP BY name
    ),
    totals AS (
        SELECT sum(duration) AS total
        FROM summary
    )
SELECT
    ids.value AS "name",
    round(summary.duration * 100.0 / (SELECT total FROM totals), 2) AS "durationRatio",
    summary.duration AS "totalTimeNs",
    summary.num AS "totalCount",
    round(summary.avg_duration, 1) AS "averageNs",
    round(summary.min_duration, 1) AS "minNs",
    round(summary.lower_quartile_duration, 1) AS "Q1Ns",
    round(summary.med_duration, 1) AS "medNs",
    round(summary.upper_quartile_duration, 1) AS "Q3Ns",
    round(summary.max_duration, 1) AS "maxNs",
    round(summary.stdev_duration, 1) AS "stdev"
FROM
    summary
LEFT JOIN
    STRING_IDS AS ids
    ON ids.id = summary.name
ORDER BY 2 DESC;
    """


class CannApiSumExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
