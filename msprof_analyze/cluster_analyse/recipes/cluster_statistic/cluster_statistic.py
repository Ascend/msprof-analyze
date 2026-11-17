# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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

import math
from collections import Counter
from contextlib import closing

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.cluster_analyse.recipes.cluster_statistic.rank_statistics import read_rank_statistics
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ClusterStatistic(BaseRecipeAnalysis):
    MAX_PENDING_RANKS = 4
    TABLE_COLUMNS = {
        "CommTimeStatistic": (
            "step",
            "rank_id",
            "group_name",
            "comm_total_time",
            "comm_transit_time",
            "comm_wait_time",
            "comm_sync_time",
            "comm_free_time",
        ),
        "TransitStatistic": (
            "step",
            "rank_id",
            "group_name",
            "band_type",
            "transit_size",
            "transit_time",
            "bandwidth",
            "package_distribution",
        ),
        "CommOpStatistic": (
            "step",
            "group_name",
            "op_name",
            "total_time",
            "min_time",
            "min_time_rank",
            "max_time",
            "max_time_rank",
            "rank_count",
        ),
    }
    FLOAT_COLUMNS = (
        "comm_total_time",
        "comm_transit_time",
        "comm_wait_time",
        "comm_sync_time",
        "comm_free_time",
        "transit_size",
        "transit_time",
        "bandwidth",
        "total_time",
        "min_time",
        "max_time",
    )

    def __init__(self, params):
        super().__init__(params)
        if self._rank_list != Constant.ALL:
            self._rank_list = list(dict.fromkeys(self._rank_list))

    @property
    def base_dir(self):
        return Constant.CLUSTER_STATISTIC

    @property
    def required_db_keys(self):
        return [Constant.ANALYSIS_DB_PATH]

    @staticmethod
    def _merge_op_statistics(op_statistics, rank_id, op_rows):
        for step, group, op, elapsed in op_rows:
            key = (step, group, op)
            if elapsed is None:
                op_statistics.setdefault(key, (None, None, None, None, None, 0))
                continue

            elapsed = float(elapsed)
            current = op_statistics.get(key)
            if current is None or current[-1] == 0:
                op_statistics[key] = (elapsed, elapsed, rank_id, elapsed, rank_id, 1)
                continue

            total, min_time, min_rank, max_time, max_rank, count = current
            if total is not None:
                total += elapsed
                if not math.isfinite(total):
                    total = None
            if elapsed < min_time:
                min_time, min_rank = elapsed, rank_id
            if elapsed > max_time:
                max_time, max_rank = elapsed, rank_id
            op_statistics[key] = (total, min_time, min_rank, max_time, max_rank, count + 1)

    def run(self, context):
        ranks = self._get_rank_db()
        usable_ranks = [entry for entry in ranks if 0 <= entry[Constant.RANK_ID] <= Constant.MAX_INTEGER]
        if len(usable_ranks) != len(ranks):
            logger.warning("Skipped %d analysis.db inputs with invalid rank IDs.", len(ranks) - len(usable_ranks))
        if not usable_ranks:
            logger.warning("No PyTorch analysis.db with a valid global rank ID was found.")
            return None
        # Ordered consumption makes ties favor the first (smallest) rank ID.
        usable_ranks.sort(key=lambda entry: entry[Constant.RANK_ID])

        time_rows = []
        transit_rows = []
        op_statistics = {}
        diagnostics = Counter()
        readable_tables = 0
        rank_statistics = context.iter_map(read_rank_statistics, usable_ranks, self.MAX_PENDING_RANKS)
        with closing(rank_statistics):
            for rank_id, statistics in rank_statistics:
                time_rows.extend(statistics.time_rows)
                transit_rows.extend(statistics.transit_rows)
                self._merge_op_statistics(op_statistics, rank_id, statistics.op_rows)
                diagnostics.update(statistics.diagnostics)
                readable_tables += statistics.readable_tables
                del statistics

        if not readable_tables:
            logger.warning("No readable CommAnalyzerTime or CommAnalyzerBandwidth table was found.")
            return None
        for reason, count in sorted(diagnostics.items()):
            if count:
                logger.warning("Cluster statistics: %d affected records or groups (%s).", count, reason)
        return self._save_db(time_rows, transit_rows, op_statistics)

    def _get_step_range(self, db_path):
        # Like the existing DB communication modes, statistics use all source steps.
        return self.DEFAULT_STEP_RANGE

    def _save_db(self, time_rows, transit_rows, op_statistics):
        op_rows = ((*key, *metrics) for key, metrics in op_statistics.items())
        written_tables = []
        for (table, columns), rows in zip(self.TABLE_COLUMNS.items(), (time_rows, transit_rows, op_rows)):
            # Preserve nullable rank IDs as Python integers through the DataFrame conversion.
            data = pd.DataFrame(rows, columns=columns, dtype=object)
            if data.empty:
                continue
            for column in data.columns.intersection(self.FLOAT_COLUMNS):
                data[column] = data[column].astype(float)
            self.dump_data(data, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, table, index=False)
            written_tables.append(table)
            del data
        return written_tables
