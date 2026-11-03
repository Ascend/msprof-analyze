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

from contextlib import contextmanager

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_data import (
    ClusterCompareDataMixin,
)
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant


class DummyRecipe(ClusterCompareDataMixin):
    DEFAULT_STEP_RANGE = BaseRecipeAnalysis.DEFAULT_STEP_RANGE
    PARALLEL_COL_NAME = "parallelType"

    def __init__(self):
        self.step_columns = ["id", "startNs", "endNs"]
        self.parallel_types = ["tp", "dp", "dp_cp", "ep_dp"]


@pytest.fixture
def recipe():
    return DummyRecipe()


@contextmanager
def _mock_exports(comm_df, group_df=None):
    """Patch CommunicationOpWithExport / ParallelGroupInfoExport for one block."""
    group_df = group_df if group_df is not None else pd.DataFrame()
    with patch(
        "msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline."
        "cluster_compare_data.CommunicationOpWithExport"
    ) as comm_mock, patch(
        "msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline."
        "cluster_compare_data.ParallelGroupInfoExport"
    ) as group_mock:
        comm_mock.return_value.read_export_db.return_value = comm_df
        group_mock.return_value.read_export_db.return_value = group_df
        yield


# ---------------------------------------------------------------------------
# _get_step_df
# ---------------------------------------------------------------------------
class TestGetStepDf:

    def test_empty_data_map_returns_empty_df_and_none(self, recipe):
        df, db_path = recipe._get_step_df({})
        assert df.empty
        assert db_path is None

    @patch(
        "msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline."
        "cluster_compare_data.DatabaseService"
    )
    def test_default_step_range_queries_database(self, mock_db_service, recipe):
        mock_service = MagicMock()
        mock_service.query_data.return_value = {
            Constant.TABLE_STEP_TIME: pd.DataFrame(
                {"id": [1], "startNs": [0], "endNs": [100]}
            )
        }
        mock_db_service.return_value = mock_service

        data_map = {
            Constant.PROFILER_DB_PATH: "/tmp/profiler.db",
            Constant.STEP_RANGE: DummyRecipe.DEFAULT_STEP_RANGE,
        }
        df, db_path = recipe._get_step_df(data_map)

        assert db_path == "/tmp/profiler.db"
        assert not df.empty
        assert df.iloc[0]["id"] == 1
        mock_service.add_table_for_query.assert_called_once()
        mock_service.query_data.assert_called_once()


# ---------------------------------------------------------------------------
# _first_value
# ---------------------------------------------------------------------------
class TestFirstValue:

    def test_none_df_returns_default(self):
        assert ClusterCompareDataMixin._first_value(None, "col", default=5) == 5

    def test_empty_df_returns_default(self):
        assert ClusterCompareDataMixin._first_value(pd.DataFrame(), "col", default="x") == "x"

    def test_missing_column_returns_default(self):
        df = pd.DataFrame({"a": [1]})
        assert ClusterCompareDataMixin._first_value(df, "b", default=-1) == -1

    def test_returns_first_value(self):
        df = pd.DataFrame({"a": [10, 20]})
        assert ClusterCompareDataMixin._first_value(df, "a") == 10


# ---------------------------------------------------------------------------
# _get_rank_count
# ---------------------------------------------------------------------------
class TestGetRankCount:

    def test_none_df_returns_zero(self):
        assert ClusterCompareDataMixin._get_rank_count(None, "dp") == 0

    def test_empty_df_returns_zero(self):
        assert ClusterCompareDataMixin._get_rank_count(pd.DataFrame(), "dp") == 0

    def test_missing_columns_returns_zero(self):
        df = pd.DataFrame({"group_name": ["dp"]})
        assert ClusterCompareDataMixin._get_rank_count(df, "dp") == 0

    def test_matching_group_returns_rank_count(self):
        df = pd.DataFrame({"group_name": ["dp", "tp"], "rank_count": [8, 4]})
        assert ClusterCompareDataMixin._get_rank_count(df, "dp") == 8

    def test_no_matching_group_returns_zero(self):
        df = pd.DataFrame({"group_name": ["tp"], "rank_count": [4]})
        assert ClusterCompareDataMixin._get_rank_count(df, "dp") == 0


# ---------------------------------------------------------------------------
# get_total_step_duration
# ---------------------------------------------------------------------------
class TestGetTotalStepDuration:

    def test_empty_step_df_returns_zero_and_none(self, recipe):
        with patch.object(recipe, "_get_step_df", return_value=(pd.DataFrame(), "/tmp/db")):
            duration, step_id = recipe.get_total_step_duration({})
            assert duration == 0
            assert step_id is None

    def test_returns_min_duration_and_step_id(self, recipe):
        step_df = pd.DataFrame(
            {"id": [1, 2, 3], "startNs": [0, 0, 0], "endNs": [100, 50, 200]}
        )
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")):
            duration, step_id = recipe.get_total_step_duration({})
            assert duration == 50
            assert step_id == 2


# ---------------------------------------------------------------------------
# get_linearity_df
# ---------------------------------------------------------------------------
class TestGetLinearityDf:

    @patch(
        "msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline."
        "cluster_compare_data.LinearityUtils.compute_linearity_df"
    )
    def test_delegates_to_linearity_utils(self, mock_compute, recipe):
        expected = pd.DataFrame({"x": [1]})
        mock_compute.return_value = expected

        result = recipe.get_linearity_df(
            data_map={"k": "v"}, analysis_class=MagicMock, target_step_id=3,
        )

        assert result is expected
        mock_compute.assert_called_once()
        _, kwargs = mock_compute.call_args
        assert kwargs["target_step_id"] == 3
        assert kwargs["parallel_types"] == recipe.parallel_types
        assert kwargs["use_merge"] is False


# ---------------------------------------------------------------------------
# _analyze_data_by_step（核心逻辑）
# ---------------------------------------------------------------------------
class TestAnalyzeDataByStep:

    def test_empty_step_df_returns_empty_dict(self, recipe):
        with patch.object(recipe, "_get_step_df", return_value=(pd.DataFrame(), "/tmp/db")):
            assert recipe._analyze_data_by_step({}, MagicMock) == {}

    def test_target_step_id_not_found_returns_empty_dict(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [100]})
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")):
            assert recipe._analyze_data_by_step(
                {Constant.STEP_RANGE: "0,1"}, MagicMock, target_step_id=999
            ) == {}

    def test_no_communication_df_returns_empty_dict(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [100]})
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(pd.DataFrame()):
            assert recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock) == {}

    def test_zero_duration_step_skipped(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [100], "endNs": [100]})
        comm_df = pd.DataFrame({
            "startNs": [100], "endNs": [100],
            "parallelType": ["tp"], "opType": ["allReduce"], "count": [200],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            assert recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock) == {}

    def test_tail_small_allreduce_does_not_move_reference_boundary(self, recipe):
        """防回归：last_allreduce_idx 必须取自带 count>100 过滤的 tp_allreduce，
        否则尾部小 allReduce 会把参考边界后移，中间的 reduceScatter 落不进
        backward_gradient_ret。
        """
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs":      [10,   200,           400],
            "endNs":        [100,  300,           500],
            "parallelType": ["tp", "dp_cp",       "tp"],
            "opType":       ["allReduce", "reduceScatter", "allReduce"],
            "count":        [200,  50,            30],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        assert 1 in result
        assert not result[1]["backward_gradient_ret"].empty
        assert result[1]["backward_gradient_ret"]["opType"].tolist() == ["reduceScatter"]


# ---------------------------------------------------------------------------
# 补充场景：4 阶段正常归类 / 无 TP allReduce / result1 空 / 跨边界 / NaN
# ---------------------------------------------------------------------------
class TestAnalyzeDataByStepExtended:

    def test_four_phases_normal_classification(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs":      [10,   150,  200,  320,  400],
            "endNs":        [100,  180,  300,  350,  450],
            "parallelType": ["dp_cp", "dp", "tp", "dp_cp", "dp"],
            "opType":       ["allGather", "allReduce", "allReduce",
                             "reduceScatter", "allReduce"],
            "count":        [50,   50,   200,  50,   50],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        ret = result[1]
        assert ret["forward_ret"]["opType"].tolist() == ["allGather"]
        assert ret["forward_ret"]["startNs"].tolist() == [10]
        assert ret["forward_backward_ret"]["parallelType"].tolist() == ["dp"]
        assert ret["forward_backward_ret"]["startNs"].tolist() == [150]
        assert ret["backward_gradient_ret"]["opType"].tolist() == ["reduceScatter"]
        assert ret["backward_optimizer_ret"]["opType"].tolist() == ["allReduce"]
        assert ret["backward_optimizer_ret"]["parallelType"].tolist() == ["dp"]

    def test_no_tp_allreduce_skips_phase2_3_4(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs":      [10,   20],
            "endNs":        [100,  200],
            "parallelType": ["dp_cp", "dp_cp"],
            "opType":       ["allGather", "reduceScatter"],
            "count":        [50,   50],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        ret = result[1]
        assert ret["forward_ret"].empty
        assert ret["forward_backward_ret"].empty
        assert ret["backward_gradient_ret"].empty
        assert ret["backward_optimizer_ret"].empty

    def test_result1_empty_skips_phase2(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs":      [200,  320,  400],
            "endNs":        [300,  350,  450],
            "parallelType": ["tp", "dp_cp", "dp"],
            "opType":       ["allReduce", "reduceScatter", "allReduce"],
            "count":        [200,  50,   50],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        ret = result[1]
        assert ret["forward_ret"].empty
        assert ret["forward_backward_ret"].empty
        assert ret["backward_gradient_ret"]["opType"].tolist() == ["reduceScatter"]
        assert ret["backward_optimizer_ret"]["parallelType"].tolist() == ["dp"]

    def test_concrete_step_range_from_dict_raises_keyerror(self, recipe):
        """Document the current defect: when STEP_RANGE overrides the default
        range, _get_step_df returns a one-column df (column 0) without
        id/startNs/endNs, so _analyze_data_by_step raises KeyError on startNs.

        Once the branch is fixed to return a proper step df, this test will
        fail (KeyError is no longer raised) and must be rewritten as a normal
        classification assertion.
        """
        data_map = {
            Constant.PROFILER_DB_PATH: "/tmp/profiler.db",
            Constant.STEP_RANGE: "10,20",
        }
        step_df, _ = recipe._get_step_df(data_map)
        for col in ("id", "startNs", "endNs"):
            assert col not in step_df.columns

        comm_df = pd.DataFrame({
            "startNs": [10], "endNs": [20],
            "parallelType": ["tp"], "opType": ["allReduce"], "count": [200],
        })
        with _mock_exports(comm_df), pytest.raises(KeyError, match="startNs"):
            recipe._analyze_data_by_step(data_map, MagicMock)

    def test_result3_excludes_reduce_scatter_crossing_step_boundary(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [500]})
        comm_df = pd.DataFrame({
            "startNs":      [100,  300,  450],
            "endNs":        [200,  400,  600],
            "parallelType": ["tp", "dp_cp", "dp_cp"],
            "opType":       ["allReduce", "reduceScatter", "reduceScatter"],
            "count":        [200,  50,   50],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        starts = result[1]["backward_gradient_ret"]["startNs"].tolist()
        assert 300 in starts
        assert 450 not in starts

    def test_optype_with_nan_does_not_raise(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs":      [10,   200,  320],
            "endNs":        [100,  300,  350],
            "parallelType": ["dp_cp", "tp", "dp_cp"],
            "opType":       ["allGather", "allReduce", None],
            "count":        [50,   200,  50],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        assert result[1]["forward_ret"]["opType"].tolist() == ["allGather"]

    def test_analyse_ret_does_not_carry_full_communication_ref(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs": [10, 200], "endNs": [100, 300],
            "parallelType": ["tp", "tp"],
            "opType": ["allReduce", "allReduce"], "count": [200, 200],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        assert "communication" not in result[1]

    def test_rank_counts_propagated_to_analyse_ret(self, recipe):
        step_df = pd.DataFrame({"id": [1], "startNs": [0], "endNs": [1000]})
        comm_df = pd.DataFrame({
            "startNs": [10], "endNs": [100],
            "parallelType": ["tp"], "opType": ["allReduce"], "count": [200],
        })
        group_df = pd.DataFrame({
            "group_name": ["dp", "dp_cp", "ep_dp"],
            "rank_count": [8, 16, 4],
        })
        with patch.object(recipe, "_get_step_df", return_value=(step_df, "/tmp/db")), \
                _mock_exports(comm_df, group_df):
            result = recipe._analyze_data_by_step({Constant.STEP_RANGE: "0,1"}, MagicMock)

        assert result[1]["max_dp_rank"] == 8
        assert result[1]["max_dp_cp_rank"] == 16
        assert result[1]["max_ep_dp_rank"] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
