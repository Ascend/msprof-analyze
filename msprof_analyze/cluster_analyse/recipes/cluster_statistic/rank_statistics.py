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
import math
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from itertools import groupby

from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.common_func.utils import double_hash
from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()

TIME_METRICS = ("elapse_time", "transit_time", "wait_time", "synchronization_time", "idle_time")
TIME_COLUMNS = ("step", "group_name", "hccl_op_name", "type", *TIME_METRICS)
BANDWIDTH_COLUMNS = (
    "step",
    "group_name",
    "transport_type",
    "hccl_op_name",
    "type",
    "transit_size",
    "transit_time",
    "package_size",
    "count",
)
COMMUNICATION_TYPES = {Constant.COLLECTIVE, Constant.P2P}


@dataclass
class RankStatistics:
    time_rows: list = field(default_factory=list)
    op_rows: list = field(default_factory=list)
    transit_rows: list = field(default_factory=list)
    group_types: dict = field(default_factory=dict)
    parallel_groups: dict = field(default_factory=dict)
    diagnostics: Counter = field(default_factory=Counter)
    readable_tables: int = 0


def _metric(value):
    if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
        return value
    return None


def _add_metric(total, value):
    if total is None or value is None:
        return None
    return _metric(total + value)


def _group_type(value):
    return value.lower() if isinstance(value, str) else None


def _valid_keys(*values):
    return all(isinstance(value, str) and value.strip() for value in values)


def _read_time(rows, rank_id, result):
    totals_by_group = {}
    for step, group, op, source_type, *raw_metrics in rows:
        group_type = _group_type(source_type)
        if not _valid_keys(step, group, op) or group_type not in COMMUNICATION_TYPES:
            result.diagnostics["invalid time record keys or type"] += 1
            continue
        result.group_types.setdefault(group, group_type)

        metrics = tuple(_metric(value) for value in raw_metrics)
        current = totals_by_group.get((step, group), (0.0,) * len(TIME_METRICS))
        totals_by_group[step, group] = tuple(_add_metric(total, value) for total, value in zip(current, metrics))

        elapsed = metrics[0]
        valid_rank = rank_id if elapsed is not None else None
        result.op_rows.append(
            (step, group, op, elapsed, elapsed, valid_rank, elapsed, valid_rank, int(elapsed is not None))
        )

    for (step, group), totals in totals_by_group.items():
        for name, total in zip(TIME_METRICS, totals):
            if total is None:
                result.diagnostics[f"unavailable time metric {name}"] += 1
        result.time_rows.append((step, rank_id, group, *totals))


def _bandwidth_rows(rows, result):
    for step, group, band, op, source_type, *metrics in rows:
        group_type = _group_type(source_type)
        if not _valid_keys(step, group, band, op) or group_type not in COMMUNICATION_TYPES:
            result.diagnostics["invalid bandwidth record keys or type"] += 1
            continue
        result.group_types.setdefault(group, group_type)
        yield step, group, band, op, *metrics


def _read_bandwidth(rows, rank_id, result):
    for (step, group, band), band_rows in groupby(_bandwidth_rows(rows, result), key=lambda row: row[:3]):
        totals = (0.0, 0.0)
        packages = {}
        has_invalid_size = False
        for _, op_rows in groupby(band_rows, key=lambda row: row[3]):
            op_totals = None
            for _, _, _, _, size, time, package_size, count in op_rows:
                metrics = (_metric(size), _metric(time))
                if op_totals is None:
                    op_totals = metrics
                else:
                    op_totals = tuple(
                        previous if previous == value else None for previous, value in zip(op_totals, metrics)
                    )
                package_size = _metric(package_size)
                if package_size is None:
                    has_invalid_size = True
                    continue
                count = _metric(count)
                count = int(count) if count is not None and count == int(count) else None
                previous_count = packages.get(package_size, 0)
                packages[package_size] = None if previous_count is None or count is None else previous_count + count
            totals = tuple(_add_metric(total, value) for total, value in zip(totals, op_totals))

        size, time = totals
        bandwidth = None
        if size is not None and time is not None:
            if time > 0:
                bandwidth = _metric(size / time)
            elif size == 0:
                bandwidth = 0.0
        for name, value in zip(("transit_size", "transit_time", "bandwidth"), (size, time, bandwidth)):
            if value is None:
                result.diagnostics[f"unavailable transmission metric {name}"] += 1
        if has_invalid_size:
            result.diagnostics["invalid package size"] += 1
            distribution = None
        else:
            result.diagnostics["unavailable package count"] += sum(count is None for count in packages.values())
            distribution = json.dumps(
                [{"package_size": size, "count": count} for size, count in sorted(packages.items())],
                allow_nan=False,
                separators=(",", ":"),
            )
        result.transit_rows.append((step, rank_id, group, band, size, time, bandwidth, distribution))


def _read_table(cursor, table, columns, aggregate, rank_id, db_path, order_by=""):
    result = RankStatistics()
    try:
        available = set(DBManager.get_table_columns_name(cursor, table))
        if not available:
            logger.warning("Rank %s: missing or unreadable %s in %s.", rank_id, table, db_path)
            return result
        missing = set(columns) - available
        if missing:
            logger.warning("Rank %s: skipping %s in %s, missing fields %s.", rank_id, table, db_path, sorted(missing))
            return result
        # Identifiers and ordering are supplied by the fixed source schema.
        query = f"SELECT {', '.join(columns)} FROM {table} WHERE hccl_op_name IS NOT ? {order_by}"  # nosec B608
        aggregate(cursor.execute(query, (Constant.TOTAL_OP_INFO,)), rank_id, result)
    except sqlite3.Error as err:
        logger.warning("Rank %s: cannot read %s in %s: %s", rank_id, table, db_path, err)
        return RankStatistics()
    result.readable_tables = 1
    return result


def _read_parallel_groups(db_path, group_types):
    if not db_path or not group_types:
        return {}
    try:
        PathManager.check_input_file_path(db_path)
        source, cursor = DBManager.create_connect_db(db_path)
        if not source:
            return {}
        with closing(source), closing(cursor):
            if not DBManager.get_table_columns_name(cursor, Constant.TABLE_META_DATA):
                return {}
            rows = cursor.execute("SELECT value FROM META_DATA WHERE name = ?", (Constant.PARALLEL_GROUP_INFO,))
            groups = {}
            for (value,) in rows:
                for group_id, info in json.loads(value).items():
                    group = str(double_hash(group_id))
                    ranks = sorted(info.get(CommunicationGroupMap.GLOBAL_RANKS, []))
                    rank_set = "(" + ",".join(str(rank) for rank in ranks) + ")"
                    if group in group_types:
                        groups[group] = (group_id, info.get(TableConstant.GROUP_NAME, ""), rank_set)
            if any(not isinstance(name, str) for _, name, _ in groups.values()):
                raise ValueError("Invalid parallel group name")
            return groups
    except (sqlite3.Error, OSError, RuntimeError, ValueError, TypeError, AttributeError) as err:
        logger.warning("Cannot read optional parallel group information in %s: %s", db_path, err)
        return {}


def read_rank_statistics(rank_db):
    rank_id = rank_db[Constant.RANK_ID]
    db_path = rank_db[Constant.ANALYSIS_DB_PATH]
    try:
        PathManager.check_input_file_path(db_path)
        source, cursor = DBManager.create_connect_db(db_path)
        if not source:
            logger.warning("Rank %s: cannot open %s.", rank_id, db_path)
            return rank_id, RankStatistics()
        with closing(source), closing(cursor):
            cursor.execute("BEGIN")
            time_stats = _read_table(
                cursor, Constant.TABLE_COMM_ANALYZER_TIME, TIME_COLUMNS, _read_time, rank_id, db_path
            )
            transit_stats = _read_table(
                cursor,
                Constant.TABLE_COMM_ANALYZER_BANDWIDTH,
                BANDWIDTH_COLUMNS,
                _read_bandwidth,
                rank_id,
                db_path,
                "ORDER BY step, group_name, transport_type, hccl_op_name",
            )
    except (sqlite3.Error, OSError, RuntimeError, ValueError) as err:
        logger.warning("Rank %s: cannot read %s: %s", rank_id, db_path, err)
        return rank_id, RankStatistics()

    time_stats.transit_rows = transit_stats.transit_rows
    for group, group_type in transit_stats.group_types.items():
        time_stats.group_types.setdefault(group, group_type)
    time_stats.parallel_groups = _read_parallel_groups(rank_db[Constant.PROFILER_DB_PATH], time_stats.group_types)
    time_stats.diagnostics.update(transit_stats.diagnostics)
    time_stats.readable_tables += transit_stats.readable_tables
    return rank_id, time_stats
