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

import sys
from collections import Counter
from contextlib import closing

import pandas as pd

from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.cluster_analyse.recipes.cluster_statistic.rank_statistics import read_rank_statistics
from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ClusterStatistic(BaseRecipeAnalysis):
    TABLES = ("CommTimeStatistic", "TransitStatistic", "CommOpStatistic")
    MAX_PENDING_RANKS = 4
    CREATE_TABLES = (
        """CREATE TABLE {schema}.CommTimeStatistic (
            step TEXT, rank_id INTEGER, group_name TEXT, comm_total_time REAL,
            comm_transit_time REAL, comm_wait_time REAL, comm_sync_time REAL, comm_free_time REAL
        )""",
        """CREATE TABLE {schema}.TransitStatistic (
            step TEXT, rank_id INTEGER, group_name TEXT, band_type VARCHAR(100),
            transit_size REAL, transit_time REAL, bandwidth REAL, package_distribution JSON
        )""",
        """CREATE TABLE {schema}.CommOpStatistic (
            step TEXT, group_name TEXT, op_name VARCHAR(100), total_time REAL,
            min_time REAL, min_time_rank INTEGER, max_time REAL, max_time_rank INTEGER, rank_count INTEGER,
            PRIMARY KEY (step, group_name, op_name)
        )""",
    )
    CREATE_GROUP_MEMBERS = """CREATE TEMP TABLE StatisticGroupMembers (
        group_name TEXT, rank_id INTEGER, type TEXT,
        PRIMARY KEY (group_name, rank_id)
    ) WITHOUT ROWID"""
    UPSERT_OP = """
        INSERT INTO temp.CommOpStatistic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(step, group_name, op_name) DO UPDATE SET
            total_time = CASE
                WHEN CommOpStatistic.rank_count = 0 THEN excluded.total_time
                WHEN excluded.rank_count = 0 THEN CommOpStatistic.total_time
                WHEN CommOpStatistic.total_time + excluded.total_time <= ?10
                    THEN CommOpStatistic.total_time + excluded.total_time
                ELSE NULL END,
            min_time_rank = CASE
                WHEN CommOpStatistic.min_time IS NULL OR excluded.min_time < CommOpStatistic.min_time
                    THEN excluded.min_time_rank
                ELSE CommOpStatistic.min_time_rank END,
            min_time = CASE
                WHEN CommOpStatistic.min_time IS NULL OR excluded.min_time < CommOpStatistic.min_time
                    THEN excluded.min_time ELSE CommOpStatistic.min_time END,
            max_time_rank = CASE
                WHEN CommOpStatistic.max_time IS NULL OR excluded.max_time > CommOpStatistic.max_time
                    THEN excluded.max_time_rank
                ELSE CommOpStatistic.max_time_rank END,
            max_time = CASE
                WHEN CommOpStatistic.max_time IS NULL OR excluded.max_time > CommOpStatistic.max_time
                    THEN excluded.max_time ELSE CommOpStatistic.max_time END,
            rank_count = CommOpStatistic.rank_count + excluded.rank_count
    """

    def __init__(self, params, connection):
        super().__init__(params)
        if self._rank_list != Constant.ALL:
            self._rank_list = list(dict.fromkeys(self._rank_list))
        self.connection = connection

    @property
    def base_dir(self):
        return Constant.CLUSTER_STATISTIC

    @property
    def required_db_keys(self):
        return [Constant.ANALYSIS_DB_PATH]

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

        # Stage the results from the shared rank scan without locking the output database for writing.
        for statement in self.CREATE_TABLES:
            self.connection.execute(statement.format(schema="temp"))
        self.connection.execute(self.CREATE_GROUP_MEMBERS)
        diagnostics = Counter()
        readable_tables = 0
        parallel_groups = {}
        rank_statistics = context.iter_map(read_rank_statistics, usable_ranks, self.MAX_PENDING_RANKS)
        with closing(rank_statistics), self.connection:
            for rank_id, statistics in rank_statistics:
                self._write_rank(rank_id, statistics)
                for group, metadata in statistics.parallel_groups.items():
                    if parallel_groups.setdefault(group, metadata) != metadata:
                        parallel_groups[group] = None
                diagnostics.update(statistics.diagnostics)
                readable_tables += statistics.readable_tables

        if not readable_tables:
            logger.warning("No readable CommAnalyzerTime or CommAnalyzerBandwidth table was found.")
            return None
        for reason, count in sorted(diagnostics.items()):
            if count:
                logger.warning("Cluster statistics: %d affected records or groups (%s).", count, reason)
        self._save_db()
        return self._group_mapping_input(parallel_groups)

    def _group_mapping_input(self, parallel_groups):
        members = pd.DataFrame.from_records(
            self.connection.execute(
                "SELECT group_name, rank_id, type FROM StatisticGroupMembers ORDER BY group_name, rank_id"
            ),
            columns=[TableConstant.GROUP_NAME, TableConstant.RANK_ID, TableConstant.TYPE],
        )
        # Keep one source type per group, using the lowest observed rank.
        members[TableConstant.TYPE] = members.groupby(TableConstant.GROUP_NAME, sort=False)[
            TableConstant.TYPE
        ].transform("first")

        metadata = []
        for group, info in parallel_groups.items():
            if info is None:
                logger.warning("Conflicting parallel group metadata for %s; using observed ranks.", group)
                continue
            group_id, name, rank_set = info
            metadata.append((group, group_id, name, "" if rank_set == "()" else rank_set))
        parallel_info = pd.DataFrame.from_records(
            metadata,
            columns=[
                TableConstant.GROUP_NAME,
                TableConstant.GROUP_ID,
                TableConstant.PG_NAME,
                CommunicationGroupMap.GLOBAL_RANKS,
            ],
        )
        return [(members, parallel_info)]

    def _get_step_range(self, db_path):
        # Like the existing DB communication modes, statistics use all source steps.
        return self.DEFAULT_STEP_RANGE

    def _write_rank(self, rank_id, statistics):
        self.connection.executemany(
            "INSERT INTO temp.CommTimeStatistic VALUES (?, ?, ?, ?, ?, ?, ?, ?)", statistics.time_rows
        )
        self.connection.executemany(
            "INSERT INTO temp.TransitStatistic VALUES (?, ?, ?, ?, ?, ?, ?, ?)", statistics.transit_rows
        )
        self.connection.executemany(self.UPSERT_OP, ((*row, sys.float_info.max) for row in statistics.op_rows))
        self.connection.executemany(
            "INSERT INTO StatisticGroupMembers VALUES (?, ?, ?)",
            ((group, rank_id, group_type) for group, group_type in statistics.group_types.items()),
        )

    def _save_db(self):
        for table, statement in zip(self.TABLES, self.CREATE_TABLES):
            with self.connection:
                self.connection.execute("BEGIN IMMEDIATE")
                self.connection.execute(f"DROP TABLE IF EXISTS main.{table}")  # nosec B608
                self.connection.execute(statement.format(schema="main"))
                self.connection.execute(f"INSERT INTO main.{table} SELECT * FROM temp.{table}")  # nosec B608
            self.connection.execute(f"DROP TABLE temp.{table}")  # nosec B608
