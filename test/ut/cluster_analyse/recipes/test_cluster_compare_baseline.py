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

import os
import tempfile
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline import (
    cluster_compare_baseline as mod,
)
from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_baseline import (
    ClusterCompareBaseline,
    logger as module_logger,
)

RECIPE = "cluster_compare_baseline"
BASELINE_MODULE = (
    "msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_baseline"
)
ALLOC_MODULE = (
    "msprof_analyze.cluster_analyse.cluster_data_preprocess.prof_data_allocate.ProfDataAllocate"
)


def _make_linearity(rows):
    return pd.DataFrame(
        [
            {
                "id": 1,
                "parallelType": pt,
                "totalTimeWithoutCommunicationBlackout": total,
                "ratioOfUnmaskedCommunication": unmasked,
            }
            for pt, total, unmasked in rows
        ]
    )


def _make_comparison(rows):
    return pd.DataFrame(
        [{"parallelType": pt, "diff": diff, "diff_percent": pct} for pt, diff, pct in rows]
    )


class ClusterCompareBaselineTest(unittest.TestCase):
    def _new_recipe(self):
        obj = ClusterCompareBaseline.__new__(ClusterCompareBaseline)
        obj.text_reports = []
        obj.operator_reports = []
        obj._rank_list = "all"
        obj._recipe_name = RECIPE
        obj._prof_type = "NPU"
        obj._data_map = {}
        obj._baseline_data_map = {}
        obj.db_paths = []
        obj.baseline_db_paths = []
        obj.rank_data_map = {}
        obj._current_report_rank_id = 0
        return obj

    def _patch_output_path(self, recipe):
        tmp = tempfile.mkdtemp()
        patcher = patch.object(
            type(recipe), "output_path", new_callable=PropertyMock, return_value=tmp
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return tmp

    def _run_with(self, recipe, current_lin, comparison, step_times, baseline_lin=None, save_patch=True):
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}]
        recipe.rank_data_map = {0: {"current": {}, "baseline": {}}}
        recipe.get_total_step_duration = MagicMock(side_effect=step_times)
        if baseline_lin is not None:
            recipe.get_linearity_df = MagicMock(side_effect=[baseline_lin, current_lin])
        else:
            recipe.get_linearity_df = MagicMock(return_value=current_lin)
        recipe.compare_by_parallel_type = MagicMock(return_value=comparison)
        if save_patch:
            with patch.object(recipe, "_save_text_report"):
                recipe.run(None)
        else:
            recipe.run(None)

    # ==================================================================
    # __init__ / has_baseline
    # ==================================================================
    def test_build_rank_data_map_intersection(self):
        recipe = self._new_recipe()
        recipe.db_paths = [
            {Constant.RANK_ID: 0, "name": "current-0"},
            {Constant.RANK_ID: 1, "name": "current-1"},
        ]
        recipe.baseline_db_paths = [
            {Constant.RANK_ID: 1, "name": "baseline-1"},
            {Constant.RANK_ID: 2, "name": "baseline-2"},
        ]
        rank_data_map = recipe._build_rank_data_map()
        self.assertEqual(set(rank_data_map), {1})
        self.assertEqual(rank_data_map[1]["current"]["name"], "current-1")
        self.assertEqual(rank_data_map[1]["baseline"]["name"], "baseline-1")

    def test_build_rank_data_map_ignores_none_rank_id(self):
        recipe = self._new_recipe()
        recipe.db_paths = [{Constant.RANK_ID: 0}, {Constant.RANK_ID: None}]
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}, {Constant.RANK_ID: None}]
        self.assertEqual(set(recipe._build_rank_data_map()), {0})

    def test_has_baseline_false_when_empty(self):
        recipe = self._new_recipe()
        recipe.baseline_db_paths = []
        self.assertFalse(recipe.has_baseline)

    def test_has_baseline_true_when_present(self):
        recipe = self._new_recipe()
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}]
        self.assertTrue(recipe.has_baseline)

    def test_rank_list_filter(self):
        recipe = self._new_recipe()
        recipe._rank_list = [1]
        recipe.db_paths = [{Constant.RANK_ID: 0}, {Constant.RANK_ID: 1}]
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}, {Constant.RANK_ID: 1}]
        self.assertEqual(set(recipe._build_rank_data_map()), {1})

    def test_rank_list_all_uses_intersection(self):
        recipe = self._new_recipe()
        recipe._rank_list = "all"
        recipe.db_paths = [{Constant.RANK_ID: 0}, {Constant.RANK_ID: 1}]
        recipe.baseline_db_paths = [{Constant.RANK_ID: 1}, {Constant.RANK_ID: 2}]
        self.assertEqual(set(recipe._build_rank_data_map()), {1})

    # ==================================================================
    # no baseline / no shared rank  (review #8)
    # ==================================================================
    def test_run_no_baseline_writes_message(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = []
        with patch.object(recipe, "_save_text_report") as mock_save:
            recipe.run(None)
        mock_save.assert_called_once()
        self.assertTrue(any("未提供或无法加载基线数据" in t for t in recipe.text_reports))

    def test_run_no_shared_rank_writes_message(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}]
        recipe.rank_data_map = {}
        with patch.object(recipe, "_save_text_report") as mock_save:
            recipe.run(None)
        mock_save.assert_called_once()
        self.assertTrue(any("没有共同的 rank" in t for t in recipe.text_reports))

    # ==================================================================
    # _load_baseline_data degrade
    # ==================================================================
    @patch(ALLOC_MODULE)
    def test_load_baseline_data_allocate_failed_returns_empty(self, mock_alloc):
        recipe = self._new_recipe()
        mock_alloc.return_value.allocate_prof_data.return_value = False
        self.assertEqual(recipe._load_baseline_data("/no/such/path"), {})

    @patch(ALLOC_MODULE)
    def test_load_baseline_data_empty_map_returns_empty(self, mock_alloc):
        recipe = self._new_recipe()
        inst = mock_alloc.return_value
        inst.allocate_prof_data.return_value = True
        inst.data_map = {}
        inst.prof_type = "NPU"
        inst.data_type = "x"
        self.assertEqual(recipe._load_baseline_data("/path"), {})

    @patch(ALLOC_MODULE)
    def test_load_baseline_data_type_mismatch_still_returns_map(self, mock_alloc):
        recipe = self._new_recipe()
        recipe._data_map = {0: {Constant.RANK_ID: 0}}
        inst = mock_alloc.return_value
        inst.allocate_prof_data.return_value = True
        inst.data_map = {0: {Constant.RANK_ID: 0}}
        inst.prof_type = "GPU"
        inst.data_type = "x"
        with self.assertLogs(module_logger, level="WARNING") as log_ctx:
            result = recipe._load_baseline_data("/path")
        self.assertEqual(result, inst.data_map)
        self.assertTrue(any("does not match" in msg for msg in log_ctx.output))

    @patch(ALLOC_MODULE)
    def test_load_baseline_data_rank_mismatch_warns(self, mock_alloc):
        recipe = self._new_recipe()
        recipe._data_map = {0: {Constant.RANK_ID: 0}}
        inst = mock_alloc.return_value
        inst.allocate_prof_data.return_value = True
        inst.data_map = {0: {Constant.RANK_ID: 0}, 1: {Constant.RANK_ID: 1}}
        inst.prof_type = "NPU"
        inst.data_type = "x"
        with self.assertLogs(module_logger, level="WARNING") as log_ctx:
            recipe._load_baseline_data("/path")
        self.assertTrue(any("do not match" in msg for msg in log_ctx.output))

    # ==================================================================
    # save text report
    # ==================================================================
    def test_save_text_report_propagates_error(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.text_reports = ["x"]
        with patch(f"{BASELINE_MODULE}.FileManager") as mock_fm:
            mock_fm.create_common_file.side_effect = RuntimeError("disk full")
            with self.assertRaises(RuntimeError):
                recipe._save_text_report()

    def test_save_text_report_writes_file(self):
        recipe = self._new_recipe()
        out = self._patch_output_path(recipe)
        recipe.text_reports = ["line-1", "line-2"]
        expected_path = os.path.join(out, "cluster_compare_baseline_rank_3.txt")
        with patch(f"{BASELINE_MODULE}.FileManager") as mock_fm:
            recipe._save_text_report(rank_id=3)
        mock_fm.create_common_file.assert_called_once()
        args = mock_fm.create_common_file.call_args.args
        self.assertEqual(args[0], expected_path)
        self.assertEqual(args[1], "line-1\nline-2\n")

    def test_save_text_report_default_path_without_rank(self):
        recipe = self._new_recipe()
        out = self._patch_output_path(recipe)
        recipe.text_reports = ["x"]
        expected_path = os.path.join(out, "cluster_compare_baseline.txt")
        with patch(f"{BASELINE_MODULE}.FileManager") as mock_fm:
            recipe._save_text_report()
        self.assertEqual(mock_fm.create_common_file.call_args.args[0], expected_path)

    def test_save_text_report_noop_when_empty(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.text_reports = []
        with patch(f"{BASELINE_MODULE}.FileManager") as mock_fm:
            recipe._save_text_report(rank_id=0)
        mock_fm.create_common_file.assert_not_called()

    # ==================================================================
    # multi-rank / step alignment
    # ==================================================================
    def test_run_saves_report_per_rank(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}, {Constant.RANK_ID: 1}]
        recipe.rank_data_map = {0: {"current": {}, "baseline": {}}, 1: {"current": {}, "baseline": {}}}
        recipe.get_total_step_duration = MagicMock(return_value=(100, 1))
        recipe.get_linearity_df = MagicMock(return_value=_make_linearity([("dp", 100.0, 0.1)]))
        recipe.compare_by_parallel_type = MagicMock(return_value=_make_comparison([("dp", 10.0, 20.0)]))
        saved_rank_ids = []
        with patch.object(recipe, "_save_text_report", side_effect=lambda rid=None: saved_rank_ids.append(rid)):
            recipe.run(None)
        self.assertEqual(saved_rank_ids, [0, 1])

    def test_both_sides_use_current_min_step(self):
        """Both current and baseline linearity are filtered by current_min_step (legacy)."""
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}]
        recipe.rank_data_map = {0: {"current": {}, "baseline": {}}}
        recipe.get_total_step_duration = MagicMock(side_effect=[(100, 1), (120, 7)])
        get_lin = MagicMock(return_value=_make_linearity([("dp", 100.0, 0.1)]))
        recipe.get_linearity_df = get_lin
        recipe.compare_by_parallel_type = MagicMock(return_value=_make_comparison([("dp", 0.0, 0.0)]))
        with patch.object(recipe, "_save_text_report"):
            recipe.run(None)
        self.assertEqual(get_lin.call_args_list[0].args[2], 1)
        self.assertEqual(get_lin.call_args_list[1].args[2], 1)

    # ==================================================================
    # Stage 1 / 2 / 3
    # ==================================================================
    def test_run_with_nan_parallel_type_does_not_raise(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}]
        recipe.rank_data_map = {0: {"current": {}, "baseline": {}}}
        recipe.get_total_step_duration = MagicMock(return_value=(100, 1))
        current = _make_linearity([("dp", 100.0, 0.1), (float("nan"), 50.0, 0.2)])
        recipe.get_linearity_df = MagicMock(return_value=current)
        recipe.compare_by_parallel_type = MagicMock(
            return_value=_make_comparison([("dp", 10.0, 20.0), (float("nan"), 5.0, 5.0)])
        )
        with patch.object(recipe, "_save_text_report"):
            recipe.run(None)

    def test_stage3_skipped_on_zero_step_diff(self):
        recipe = self._new_recipe()
        self._run_with(
            recipe,
            _make_linearity([("cp", 100.0, 0.1)]),
            _make_comparison([("cp", 0.0, 0.0)]),
            step_times=[(100, 1), (100, 1)],
        )
        self.assertTrue(any("跳过未解释空闲分析" in t for t in recipe.text_reports))
        self.assertFalse(any("未被任何通信域" in t for t in recipe.text_reports))

    def test_stage3_skipped_on_negative_step_diff(self):
        recipe = self._new_recipe()
        self._run_with(
            recipe,
            _make_linearity([("cp", 100.0, 0.1)]),
            _make_comparison([("cp", 0.0, 0.0)]),
            step_times=[(100, 1), (150, 1)],
        )
        self.assertTrue(any("跳过未解释空闲分析" in t for t in recipe.text_reports))

    def test_stage3_triggered_on_large_unexplained_idle(self):
        recipe = self._new_recipe()
        self._run_with(
            recipe,
            _make_linearity([("cp", 100.0, 0.1)]),
            _make_comparison([("cp", 200.0, 0.0)]),
            step_times=[(200, 1), (100, 1)],
        )
        self.assertTrue(any("未被任何通信域" in t for t in recipe.text_reports))

    def test_stage1_triggers_four_phase_and_does_not_continue(self):
        recipe = self._new_recipe()
        self._patch_output_path(recipe)
        recipe.baseline_db_paths = [{Constant.RANK_ID: 0}]
        recipe.rank_data_map = {0: {"current": {}, "baseline": {}}}
        recipe.get_total_step_duration = MagicMock(return_value=(100, 1))
        recipe.get_linearity_df = MagicMock(return_value=_make_linearity([("cp", 100.0, 0.1)]))
        recipe.compare_by_parallel_type = MagicMock(return_value=_make_comparison([("dp", 50.0, 90.0)]))
        with patch.object(recipe, "get_dp_domain") as mock_dp, patch.object(recipe, "_save_text_report"):
            recipe.run(None)
        mock_dp.assert_called_once()
        self.assertTrue(any("启动四阶段逐 step 诊断" in t for t in recipe.text_reports))

    def test_stage2_mentions_actual_degraded_domain(self):
        recipe = self._new_recipe()
        self._run_with(
            recipe,
            current_lin=_make_linearity([("cp", 200.0, 0.5)]),
            baseline_lin=_make_linearity([("cp", 100.0, 0.1)]),
            comparison=_make_comparison([("cp", 50.0, 80.0)]),
            step_times=[(100, 1), (100, 1)],
        )
        self.assertTrue(any("通信域 cp 劣化" in t for t in recipe.text_reports))
        self.assertTrue(any("可能波及 PP/EP/TP" in t for t in recipe.text_reports))

    def test_stage2_not_triggered_when_unmask_delta_small(self):
        recipe = self._new_recipe()
        self._run_with(
            recipe,
            current_lin=_make_linearity([("cp", 100.0, 0.05)]),
            baseline_lin=_make_linearity([("cp", 100.0, 0.01)]),
            comparison=_make_comparison([("cp", 50.0, 80.0)]),
            step_times=[(100, 1), (100, 1)],
        )
        self.assertFalse(any("可能波及 PP/EP/TP" in t for t in recipe.text_reports))

    # ==================================================================
    # Four-phase shared evaluator (review #5 / #9 / #11 / #12 / #13)
    # ==================================================================
    @staticmethod
    def _op(parallel_type, op_type, start, end, count=1, data_type="FP16", group_rank=0):
        return {
            "parallelType": parallel_type,
            "opType": op_type,
            "dataType": data_type,
            "count": count,
            "startNs": start,
            "endNs": end,
            "group_rank": group_rank,
        }

    def _phase_value(
        self,
        start_time=0,
        end_time=100,
        max_dp_rank=4,
        max_dp_cp_rank=4,
        max_ep_dp_rank=4,
        forward_ret=None,
        forward_backward_ret=None,
        backward_gradient_ret=None,
        backward_optimizer_ret=None,
    ):
        empty = pd.DataFrame(columns=ClusterCompareBaseline.BUCKET_COLUMNS)
        return {
            "start_time": start_time,
            "end_time": end_time,
            "max_dp_rank": max_dp_rank,
            "max_dp_cp_rank": max_dp_cp_rank,
            "max_ep_dp_rank": max_ep_dp_rank,
            "forward_ret": empty if forward_ret is None else forward_ret,
            "forward_backward_ret": empty if forward_backward_ret is None else forward_backward_ret,
            "backward_gradient_ret": empty if backward_gradient_ret is None else backward_gradient_ret,
            "backward_optimizer_ret": empty if backward_optimizer_ret is None else backward_optimizer_ret,
        }

    def test_analyze_forward_phase_records_abnormal_matching_operator(self):
        recipe = self._new_recipe()
        # count*domain: 16*8 == 32*4 -> match requires this equality.
        current = self._phase_value(
            forward_ret=pd.DataFrame([self._op("dp_cp", "hcom_allGather_", 0, 4_000_000, count=16, group_rank=0)]),
            max_dp_cp_rank=8,
        )
        baseline = self._phase_value(
            forward_ret=pd.DataFrame([self._op("dp_cp", "hcom_allGather_", 0, 1_000_000, count=32, group_rank=0)]),
            max_dp_cp_rank=4,
        )
        recipe._analyze_forward_phase(1, current, baseline)
        self.assertEqual(len(recipe.operator_reports), 1)
        self.assertTrue(recipe.operator_reports[0]["is_abnormal"])
        # conclusion emitted exactly once outside the loop
        conclusion_count = sum(1 for t in recipe.text_reports if "通信算法选择不当" in t)
        self.assertEqual(conclusion_count, 2)  # 异常原因 + 优化建议

    def test_analyze_backward_gradient_phase_records_abnormal_reduce_scatter(self):
        recipe = self._new_recipe()
        current = self._phase_value(
            backward_gradient_ret=pd.DataFrame(
                [self._op("ep_dp", "hcom_reduceScatter_", 0, 4_000_000, count=16, group_rank=0)]
            ),
            max_ep_dp_rank=8,
        )
        baseline = self._phase_value(
            backward_gradient_ret=pd.DataFrame(
                [self._op("ep_dp", "hcom_reduceScatter_", 0, 1_000_000, count=32, group_rank=0)]
            ),
            max_ep_dp_rank=4,
        )
        recipe._analyze_backward_gradient_phase(1, current, baseline)
        self.assertEqual(recipe.operator_reports[0]["phase"], "阶段三")
        self.assertTrue(recipe.operator_reports[0]["is_abnormal"])

    def test_backward_gradient_empty_bucket_records_empty_table(self):
        """Phase 3 early-return path still records an empty operator table (review #3)."""
        recipe = self._new_recipe()
        recipe._record_operator_table = MagicMock()
        current = self._phase_value()
        baseline = self._phase_value()
        recipe._analyze_backward_gradient_phase(1, current, baseline)
        recipe._record_operator_table.assert_called_once()

    def test_optimizer_empty_bucket_records_empty_table(self):
        """Phase 4 early-return path still records an empty operator table (review #3)."""
        recipe = self._new_recipe()
        recipe._record_operator_table = MagicMock()
        current = self._phase_value()
        baseline = self._phase_value()
        recipe._analyze_optimizer_phase(1, current, baseline, step_duration=100)
        recipe._record_operator_table.assert_called_once()

    def test_evaluate_phase_operators_emits_conclusion_once(self):
        recipe = self._new_recipe()
        current_df = pd.DataFrame([
            self._op("dp_cp", "hcom_allGather_", 0, 4_000_000, count=16, group_rank=0),
            self._op("dp_cp", "hcom_allGather_", 0, 4_000_000, count=16, group_rank=1),
        ])
        baseline_df = pd.DataFrame([
            self._op("dp_cp", "hcom_allGather_", 0, 1_000_000, count=16, group_rank=0),
            self._op("dp_cp", "hcom_allGather_", 0, 1_000_000, count=16, group_rank=1),
        ])
        recipe._get_domains = MagicMock(return_value=(8, 4))
        recipe.comm_lower_bound = MagicMock(return_value={"ratio": 1.0})
        recipe._record_operator = MagicMock(return_value={})
        recipe._record_operator_table = MagicMock()
        recipe._evaluate_phase_operators(
            step_id=1, phase="阶段一", title="",
            current_df=current_df, baseline_df=baseline_df,
            current_value={}, baseline_value={},
            filter_mask=lambda df: df["parallelType"] == "dp_cp",
            conclusion="C", suggestion="S",
            require_count_domain_match=False,
        )
        abnormal_texts = [t for t in recipe.text_reports if "C" in t]
        self.assertEqual(len(abnormal_texts), 1)

    def test_phase2_does_not_require_count_domain_match(self):
        recipe = self._new_recipe()
        recipe._get_domains = MagicMock(return_value=(1536, 64))
        recipe.comm_lower_bound = MagicMock(return_value={"ratio": 1.0})
        recipe._record_operator = MagicMock(return_value={})
        recipe._record_operator_table = MagicMock()
        current_df = pd.DataFrame([
            self._op("dp", "hcom_allReduce_", 0, 30_000_000, count=2, data_type="FP32", group_rank=0),
        ])
        baseline_df = pd.DataFrame([
            self._op("dp", "hcom_allReduce_", 0, 60_000_000, count=2, data_type="FP32", group_rank=0),
        ])
        rows = recipe._evaluate_phase_operators(
            step_id=1, phase="阶段二", title="",
            current_df=current_df, baseline_df=baseline_df,
            current_value={}, baseline_value={},
            filter_mask=lambda df: df["parallelType"] == "dp",
            conclusion="C", suggestion="S",
            require_count_domain_match=False,
            count_filter=lambda c: c < 100,
        )
        self.assertEqual(len(rows), 1)

    def test_phase4_compares_with_baseline(self):
        """Current optimizer ratio (0.2) > baseline (0.1) -> heavy is reported."""
        recipe = self._new_recipe()
        recipe._record_operator = MagicMock(return_value={})
        recipe._record_operator_table = MagicMock()
        recipe._get_domains = MagicMock(return_value=(8, 4))
        recipe.comm_lower_bound = MagicMock(return_value={"ratio": 1.0})
        cur = pd.DataFrame([self._op("dp", "hcom_allReduce_", 0, 20, count=1000, data_type="FP32", group_rank=0)])
        base = pd.DataFrame([self._op("dp", "hcom_allReduce_", 0, 10, count=1000, data_type="FP32", group_rank=0)])
        recipe._analyze_optimizer_phase(
            1,
            {"backward_optimizer_ret": cur, "end_time": 100, "start_time": 0},
            {"backward_optimizer_ret": base},
            step_duration=100,
        )
        self.assertTrue(any("优化器通信过重" in t for t in recipe.text_reports))

    def test_phase4_not_triggered_when_current_not_heavier(self):
        """Current optimizer ratio (0.1) <= baseline (0.2) -> heavy is not reported."""
        recipe = self._new_recipe()
        recipe._record_operator = MagicMock(return_value={})
        recipe._record_operator_table = MagicMock()
        recipe._get_domains = MagicMock(return_value=(8, 4))
        recipe.comm_lower_bound = MagicMock(return_value={"ratio": 1.0})
        cur = pd.DataFrame([self._op("dp", "hcom_allReduce_", 0, 10, count=1000, data_type="FP32", group_rank=0)])
        base = pd.DataFrame([self._op("dp", "hcom_allReduce_", 0, 20, count=1000, data_type="FP32", group_rank=0)])
        recipe._analyze_optimizer_phase(
            1,
            {"backward_optimizer_ret": cur, "end_time": 100, "start_time": 0},
            {"backward_optimizer_ret": base},
            step_duration=100,
        )
        self.assertFalse(any("优化器通信过重" in t for t in recipe.text_reports))

    def test_phase4_does_not_filter_large_ops(self):
        """Phase 4 records large optimizer allReduce (count >= 100) instead of skipping it (review #13)."""
        recipe = self._new_recipe()
        recipe._get_domains = MagicMock(return_value=(8, 4))
        recipe.comm_lower_bound = MagicMock(return_value={"ratio": 1.0})
        recipe._record_operator = MagicMock(return_value={})
        recipe._record_operator_table = MagicMock()
        # count=2000 > SMALL_OP_COUNT_THRESHOLD (100)
        cur = pd.DataFrame([self._op("dp", "hcom_allReduce_", 0, 20, count=2000, data_type="FP32", group_rank=0)])
        base = pd.DataFrame([self._op("dp", "hcom_allReduce_", 0, 10, count=2000, data_type="FP32", group_rank=0)])
        operator_rows = recipe._evaluate_phase_operators(
            step_id=1, phase="阶段四", title="",
            current_df=cur, baseline_df=base,
            current_value={}, baseline_value={},
            filter_mask=lambda df: df["parallelType"] == "dp",
            conclusion="C", suggestion="S",
            require_count_domain_match=False,
            count_filter=None,
        )
        self.assertEqual(len(operator_rows), 1)

    def test_get_dp_domain_docstring_mentions_given_step(self):
        doc = ClusterCompareBaseline.get_dp_domain.__doc__ or ""
        self.assertIn("given step", doc)

    def test_phase_filters_phase2_and_phase4_only_dp_allreduce(self):
        self.assertEqual(ClusterCompareBaseline.PHASE_FILTERS["forward_backward"], (["dp"], ["allReduce"]))
        self.assertEqual(ClusterCompareBaseline.PHASE_FILTERS["optimizer"], (["dp"], ["allReduce"]))

    def test_conclusion_text_uses_hierarchical(self):
        """Review #2: the shared suggestion text spells 'Hierarchical' correctly."""
        self.assertIn("Hierarchical", mod.SUGGESTION_ALGO_OR_LINK)
        self.assertNotIn("Herarchical", mod.SUGGESTION_ALGO_OR_LINK)


if __name__ == "__main__":
    unittest.main()
