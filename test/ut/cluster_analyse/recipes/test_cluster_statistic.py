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

import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

from msprof_analyze.cluster_analyse.analysis.analysis_facade import AnalysisFacade
from msprof_analyze.cluster_analyse.common_func.context import ConcurrentContext, Context
from msprof_analyze.cluster_analyse.common_func.utils import double_hash
from msprof_analyze.cluster_analyse.recipes.cluster_statistic.cluster_statistic import ClusterStatistic
from msprof_analyze.cluster_analyse.recipes.cluster_statistic.rank_statistics import read_rank_statistics
from msprof_analyze.prof_common.constant import Constant


def make_rank(path, rank_id, time_rows=None, bandwidth_rows=None):
    path.mkdir()
    source_dir = path / Constant.SINGLE_OUTPUT
    source_dir.mkdir()
    analysis_db = source_dir / "analysis.db"
    with closing(sqlite3.connect(str(analysis_db))) as connection, connection:
        if time_rows is not None:
            connection.execute(
                """CREATE TABLE CommAnalyzerTime (
                    step TEXT, group_name TEXT, hccl_op_name TEXT, type TEXT, elapse_time REAL,
                    transit_time REAL, wait_time REAL, synchronization_time REAL, idle_time REAL
                )"""
            )
            connection.executemany("INSERT INTO CommAnalyzerTime VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", time_rows)
        if bandwidth_rows is not None:
            connection.execute(
                """CREATE TABLE CommAnalyzerBandwidth (
                    step TEXT, group_name TEXT, transport_type TEXT, hccl_op_name TEXT, type TEXT,
                    transit_size REAL, transit_time REAL, package_size REAL, count NUMERIC
                )"""
            )
            connection.executemany(
                "INSERT INTO CommAnalyzerBandwidth VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", bandwidth_rows
            )
    return {Constant.RANK_ID: rank_id, Constant.ANALYSIS_DB_PATH: str(analysis_db), Constant.PROFILER_DB_PATH: ""}


def test_reads_both_tables_and_preserves_step_and_full_op_name(tmp_path):
    rank = make_rank(
        tmp_path / "rank2",
        2,
        time_rows=[
            ("step12", "ring", "allreduce__1", "Collective", 10, 4, 2, 1, 4),
            ("step12", "ring", "allreduce__2", "Collective", 20, 8, 3, 2, 9),
            (None, None, "Total Op Info", None, 30, 12, 5, 3, 13),
        ],
        bandwidth_rows=[
            ("step12", "link", "RDMA", "send__1", "P2P", 100, 10, 1, 50),
            ("step12", "link", "RDMA", "send__1", "P2P", 100, 10, 0.5, 100),
            ("step12", "link", "RDMA", "send__2", "P2P", 200, 40, 0.5, 400),
        ],
    )
    _, result = read_rank_statistics(rank)
    assert result.readable_tables == 2
    assert result.time_rows == [("step12", 2, "ring", 30, 12, 5, 3, 13)]
    assert {row[2] for row in result.op_rows} == {"allreduce__1", "allreduce__2"}
    (row,) = result.transit_rows
    assert row[:-1] == ("step12", 2, "link", "RDMA", 300, 50, 6)
    assert json.loads(row[-1]) == [{"package_size": 0.5, "count": 500}, {"package_size": 1, "count": 50}]


def test_recipe_writes_statistics_when_both_source_tables_lack_step(tmp_path):
    rank_path = tmp_path / "rank0"
    rank = make_rank(rank_path, 0)
    with closing(sqlite3.connect(rank[Constant.ANALYSIS_DB_PATH])) as connection:
        connection.executescript(
            """
            CREATE TABLE CommAnalyzerTime (
                group_name TEXT, hccl_op_name TEXT, type TEXT, elapse_time REAL,
                transit_time REAL, wait_time REAL, synchronization_time REAL, idle_time REAL
            );
            INSERT INTO CommAnalyzerTime VALUES ('ring', 'allreduce__1', 'collective', 10, 4, 2, 1, 3);
            INSERT INTO CommAnalyzerTime VALUES ('ring', 'Total Op Info', 'collective', 100, 40, 20, 10, 30);
            CREATE TABLE CommAnalyzerBandwidth (
                group_name TEXT, transport_type TEXT, hccl_op_name TEXT, type TEXT,
                transit_size REAL, transit_time REAL, package_size REAL, count NUMERIC
            );
            INSERT INTO CommAnalyzerBandwidth VALUES ('ring', 'RDMA', 'allreduce__1', 'collective', 40, 4, 1, 40);
            INSERT INTO CommAnalyzerBandwidth VALUES ('ring', 'RDMA', 'Total Op Info', 'collective', 400, 40, 1, 400);
            """
        )
    params = {
        Constant.DATA_MAP: {0: str(rank_path)},
        Constant.PROFILING_TYPE: Constant.PYTORCH,
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: str(tmp_path),
    }
    with ThreadPoolExecutor(max_workers=1) as executor:
        tables = ClusterStatistic(params).run(ConcurrentContext(executor=executor))
    assert tables == ["CommTimeStatistic", "TransitStatistic", "CommOpStatistic"]

    db_path = tmp_path / Constant.CLUSTER_ANALYSIS_OUTPUT / Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT * FROM CommTimeStatistic").fetchall() == [("step", 0, "ring", 10, 4, 2, 1, 3)]
        assert connection.execute("SELECT * FROM CommOpStatistic").fetchall() == [
            ("step", "ring", "allreduce__1", 10, 10, 0, 10, 0, 1),
        ]
        (transit,) = connection.execute("SELECT * FROM TransitStatistic").fetchall()
        assert transit[:-1] == ("step", 0, "ring", "RDMA", 40, 4, 10)
        assert json.loads(transit[-1]) == [{"package_size": 1, "count": 40}]


def test_missing_source_table_and_invalid_metrics_keep_available_results(tmp_path):
    rank = make_rank(
        tmp_path / "rank0",
        0,
        bandwidth_rows=[
            ("step", "ring", "LOCAL", "op1", "collective", 0, 0, 0, 0),
            ("step", "ring", "RDMA", "op1", "collective", 2, 0, 1, -1),
            ("step", "ring", "SDMA", "op1", "collective", 10, 2, 1, 3),
            ("step", "ring", "SDMA", "op1", "collective", 20, 2, None, 3),
        ],
    )
    _, result = read_rank_statistics(rank)
    assert result.readable_tables == 1
    assert result.time_rows == []
    local, rdma, sdma = result.transit_rows
    assert local[4:7] == (0, 0, 0)
    assert rdma[4:7] == (2, 0, None)
    assert json.loads(rdma[-1]) == [{"package_size": 1, "count": None}]
    assert sdma[4:] == (None, 2, None, None)


def test_recipe_reduces_valid_ranks_and_resolves_ties_by_rank_id(tmp_path):
    data_map = {}
    max_time = sys.float_info.max
    max_rank = Constant.MAX_INTEGER
    for rank_id, elapsed, large_elapsed in [(max_rank, 12, 4), (2, 10, max_time), (1, None, max_time), (3, 12, None)]:
        rank_path = tmp_path / f"rank{rank_id}"
        make_rank(
            rank_path,
            rank_id,
            time_rows=[
                ("step7", "ring", "allreduce__1", "collective", elapsed, 4, 2, 1, 4),
                ("step7", "ring", "allreduce__2", "collective", None, 4, 2, 1, 4),
                ("step7", "ring", "allreduce__3", "collective", large_elapsed, 0, 0, 0, 0),
            ],
        )
        data_map[rank_id] = str(rank_path)
    params = {
        Constant.DATA_MAP: data_map,
        Constant.PROFILING_TYPE: Constant.PYTORCH,
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: str(tmp_path),
    }
    recipe = ClusterStatistic(params)
    db_path = tmp_path / Constant.CLUSTER_ANALYSIS_OUTPUT / Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
    with ThreadPoolExecutor(max_workers=2) as executor:
        written_tables = recipe.run(ConcurrentContext(executor=executor))
    assert written_tables == ["CommTimeStatistic", "CommOpStatistic"]
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT * FROM CommOpStatistic ORDER BY op_name").fetchall() == [
            ("step7", "ring", "allreduce__1", 34, 10, 2, 12, 3, 3),
            ("step7", "ring", "allreduce__2", None, None, None, None, None, 0),
            ("step7", "ring", "allreduce__3", None, 4, max_rank, max_time, 1, 3),
        ]
        assert connection.execute("SELECT name FROM pragma_table_info('CommOpStatistic') WHERE pk > 0").fetchall() == []
        assert connection.execute(
            "SELECT comm_total_time, comm_transit_time FROM CommTimeStatistic WHERE rank_id=2"
        ).fetchone() == (None, 8)


def test_empty_statistics_skip_table_replacement(tmp_path):
    params = {Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: str(tmp_path), Constant.EXPORT_TYPE: Constant.DB}
    recipe = ClusterStatistic(params)
    db_path = tmp_path / Constant.CLUSTER_ANALYSIS_OUTPUT / Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
    original_row = ("step1", 0, "ring", 10, 4, 2, 1, 4)
    assert recipe._save_db([], [], {}) == []
    assert not db_path.exists()
    assert recipe._save_db([original_row], [], {}) == ["CommTimeStatistic"]
    assert recipe._save_db([], [], {}) == []
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT * FROM CommTimeStatistic").fetchall() == [original_row]


def test_recipe_filters_ranks_and_keeps_all_steps(tmp_path):
    data_map = {}
    for rank_id in (0, 1):
        rank_path = tmp_path / f"rank{rank_id}"
        make_rank(
            rank_path,
            rank_id,
            time_rows=[(step, "ring", "allreduce__1", "collective", 10, 4, 2, 1, 4) for step in ("step1", "step2")],
            bandwidth_rows=[
                (step, "ring", "RDMA", "allreduce__1", "collective", 40, 4, 1, 40) for step in ("step1", "step2")
            ],
        )
        data_map[rank_id] = str(rank_path)
    params = {
        Constant.DATA_MAP: data_map,
        Constant.PROFILING_TYPE: Constant.PYTORCH,
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: str(tmp_path),
        Constant.RANK_LIST: "1,1,99",
        Constant.STEP_ID: 1,
    }
    recipe = ClusterStatistic(params)
    db_path = tmp_path / Constant.CLUSTER_ANALYSIS_OUTPUT / Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
    with ThreadPoolExecutor(max_workers=2) as executor:
        recipe.run(ConcurrentContext(executor=executor))
    with closing(sqlite3.connect(db_path)) as connection:
        expected = [("step1", 1), ("step2", 1)]
        assert connection.execute("SELECT step, rank_id FROM CommTimeStatistic ORDER BY step").fetchall() == expected
        assert connection.execute("SELECT step, rank_id FROM TransitStatistic ORDER BY step").fetchall() == expected
        assert connection.execute("SELECT step, rank_count FROM CommOpStatistic ORDER BY step").fetchall() == expected


def test_companion_tables_use_group_recipe_and_existing_cluster_metadata(tmp_path):
    (tmp_path / Constant.PROFILER_METADATA).write_text(
        json.dumps({"distributed_args": {"rank": 2, "world_size": 8}}), encoding="utf-8"
    )
    group_id = "group-id"
    ring = str(double_hash(group_id))
    data_map = {}
    for rank_id in (2, 3):
        rank_path = tmp_path / f"rank{rank_id}"
        operators = [(ring, "allreduce__1", "collective")]
        if rank_id == 2:
            operators.append(("link", "send__1", "p2p"))
        make_rank(
            rank_path,
            rank_id,
            time_rows=[("step1", group, op, kind, 10, 4, 2, 1, 3) for group, op, kind in operators],
            bandwidth_rows=[("step1", group, "RDMA", op, kind, 40, 4, 1, 40) for group, op, kind in operators],
        )
        data_map[rank_id] = str(rank_path)
    profiler_db = tmp_path / "rank2" / Constant.SINGLE_OUTPUT / "ascend_pytorch_profiler_2.db"
    with closing(sqlite3.connect(profiler_db)) as connection, connection:
        connection.execute("CREATE TABLE META_DATA (name TEXT, value TEXT)")
        connection.execute(
            "INSERT INTO META_DATA VALUES (?, ?)",
            (Constant.PARALLEL_GROUP_INFO, json.dumps({group_id: {"group_name": "dp", "global_ranks": [1, 2, 3]}})),
        )

    params = {
        Constant.COLLECTION_PATH: str(tmp_path),
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: str(tmp_path),
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.DATA_MAP: data_map,
        Constant.DATA_TYPE: Constant.DB,
        Constant.PROFILING_TYPE: Constant.PYTORCH,
    }
    db_path = tmp_path / Constant.CLUSTER_ANALYSIS_OUTPUT / Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
    db_path.parent.mkdir()
    with ThreadPoolExecutor(max_workers=2) as executor:
        with patch.object(Context, "create_context", return_value=ConcurrentContext(executor=executor)):
            AnalysisFacade(params).cluster_statistic()

    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT * FROM CommunicationGroupMapping ORDER BY type").fetchall() == [
            ("collective", "(1,2,3)", ring, group_id, "dp"),
            ("p2p", "(2)", "link", "", ""),
        ]
        key, value = connection.execute("SELECT * FROM ClusterBaseInfo").fetchone()
        assert key == "distributed_args"
        assert json.loads(value) == {"world_size": 8}
