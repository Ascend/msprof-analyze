# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
import shutil
import unittest
from unittest import mock
from unittest.mock import MagicMock

from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_advice_base import ClusterAdviceBase
from msprof_analyze.advisor.advisor_backend.cluster_advice.slow_link_advice import SlowLinkAdvice
from msprof_analyze.advisor.advisor_backend.cluster_advice.slow_rank_advice import SlowRankAdvice
from msprof_analyze.advisor.advisor_backend.cluster_advice.kernel_cluster_advice import KernelClusterAdvice
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_pipeline_advice import ClusterPipelineAdvice
from msprof_analyze.prof_common.constant import Constant


class MockChildClusterAdvice(ClusterAdviceBase):
    result_file = Constant.CLUSTER_COMM_JSON

    def __init__(self, collection_path: str):
        super().__init__(collection_path)

    def run(self):
        return True

    def output(self):
        return True


class TestClusterAdviceBase(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = "./tmp_dir"
        os.makedirs(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_compute_max_gap_ratio_with_zero_mean(self):
        result = ClusterAdviceBase.compute_max_gap_ratio([1, 2], 0)
        self.assertEqual(0, result)

    def test_compute_max_gap_ratio_with_normal_input(self):
        result = ClusterAdviceBase.compute_max_gap_ratio([3, 1], 2.0)
        self.assertEqual(1.0, result)

    def test_compute_max_gap_ratio_with_abnormal_input(self):
        with self.assertRaises(TypeError):
            ClusterAdviceBase.compute_max_gap_ratio(["name", "age"], 2.0)

    def test_path_check_with_output_path(self):
        analysis_output = os.path.join(self.tmp_dir, "cluster_analysis_output")
        os.makedirs(analysis_output)
        with open(os.path.join(analysis_output, "cluster_communication.json"), "w", encoding="utf-8") as result:
            result.write("{}")
        mock_inst = MockChildClusterAdvice(self.tmp_dir)
        mock_inst.cluster_analyze = MagicMock(name="cluster_analyze")
        mock_inst.path_check()
        mock_inst.cluster_analyze.assert_not_called()

    def test_path_check_without_output_path(self):
        os.makedirs(os.path.join(self.tmp_dir, "cluster_analysis_output"))
        mock_inst = MockChildClusterAdvice(self.tmp_dir)
        mock_inst.cluster_analyze = MagicMock(name="cluster_analyze")
        mock_inst.path_check()
        mock_inst.cluster_analyze.assert_called_once()

    def test_path_check_uses_each_advice_result_file(self):
        output_dir = os.path.join(self.tmp_dir, Constant.CLUSTER_ANALYSIS_OUTPUT)
        os.makedirs(output_dir)
        with open(os.path.join(output_dir, Constant.CLUSTER_COMM_JSON), "w", encoding="utf-8") as result:
            result.write("{}")
        for advice_cls in (SlowLinkAdvice, SlowRankAdvice):
            with self.subTest(advice=advice_cls.__name__):
                advice = advice_cls(self.tmp_dir)
                advice.cluster_analyze = MagicMock()
                advice.path_check()
                self.assertEqual(advice.cluster_analyze.call_count, int(advice_cls is SlowRankAdvice))

    def test_path_check_preserves_directory_reuse_for_other_advice(self):
        output_dir = os.path.join(self.tmp_dir, Constant.CLUSTER_ANALYSIS_OUTPUT)
        for advice_cls in (KernelClusterAdvice, ClusterPipelineAdvice):
            with self.subTest(advice=advice_cls.__name__):
                advice = advice_cls(self.tmp_dir, {})
                advice.cluster_analyze = MagicMock()
                advice.path_check()
                advice.cluster_analyze.assert_called_once()
                os.makedirs(output_dir)
                advice.cluster_analyze.reset_mock()
                advice.path_check()
                advice.cluster_analyze.assert_not_called()
                os.rmdir(output_dir)

    def test_cluster_analyze_normal(self):
        mock_inst = MockChildClusterAdvice(self.tmp_dir)
        with mock.patch("msprof_analyze.advisor.advisor_backend.cluster_advice."
                        "cluster_advice_base.Interface") as mock_if:
            mock_if_inst = mock_if.return_value
            mock_if_inst.run = MagicMock(name="run")
            mock_inst.cluster_analyze()
            mock_if_inst.run.assert_called_once()

    def test_cluster_analyze_abnormal(self):
        mock_inst = MockChildClusterAdvice(self.tmp_dir)
        with self.assertRaises(ValueError):
            with mock.patch("msprof_analyze.advisor.advisor_backend.cluster_advice."
                            "cluster_advice_base.Interface") as mock_if:
                mock_if_inst = mock_if.return_value
                mock_if_inst.run = mock.Mock(name="run", side_effect=Exception('Error!'))
                mock_inst.cluster_analyze()
                mock_if_inst.run.assert_called_once()
