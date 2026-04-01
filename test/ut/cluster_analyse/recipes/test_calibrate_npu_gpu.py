# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

import unittest
from unittest.mock import patch, MagicMock, Mock
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu import CalibrateNpuGpu
from msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer import GPUAnalyzer
from msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.comparator import Comparator
from msprof_analyze.prof_common.constant import Constant


class TestCalibrateNpuGpu(unittest.TestCase):
    def setUp(self):
        self.params = {
            Constant.COLLECTION_PATH: "/tmp",
            Constant.DATA_MAP: {},
            Constant.RECIPE_NAME: "CalibrateNpuGpu",
            Constant.PARALLEL_MODE: "concurrent",
            Constant.EXPORT_TYPE: Constant.TEXT,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "/tmp_output",
            Constant.RANK_LIST: Constant.ALL,
            Constant.EXTRA_ARGS: [
                '--baseline_profiling_path', '/fake/gpu/path',
                '--fuzzy_threshold', '0.9',
                '--dump_intermediate_results'
            ]
        }
        self.analysis = CalibrateNpuGpu(self.params)

    def test_init_params(self):
        """测试__init__方法，验证参数初始化正确"""
        self.assertIsNotNone(self.analysis.npu_module_statistic_analyzer)
        self.assertEqual(self.analysis.baseline_profiling_path, '/fake/gpu/path')
        self.assertEqual(self.analysis.fuzzy_threshold, 0.9)
        self.assertTrue(self.analysis.dump_intermediate_results)

    def test_init_with_default_fuzzy_threshold(self):
        """测试__init__方法，使用默认fuzzy_threshold值"""
        params = {
            Constant.COLLECTION_PATH: "/tmp",
            Constant.DATA_MAP: {},
            Constant.RECIPE_NAME: "CalibrateNpuGpu",
            Constant.PARALLEL_MODE: "concurrent",
            Constant.EXPORT_TYPE: Constant.TEXT,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "/tmp_output",
            Constant.RANK_LIST: Constant.ALL,
            Constant.EXTRA_ARGS: [
                '--baseline_profiling_path', '/fake/gpu/path'
            ]
        }
        analysis = CalibrateNpuGpu(params)
        self.assertEqual(analysis.fuzzy_threshold, 0.8)

    def test_base_dir_property(self):
        """测试base_dir属性返回正确"""
        self.assertEqual(self.analysis.base_dir, 'calibrate_npu_gpu')

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.ExcelUtils")
    def test_agg_kernel_normal(self, mock_excel_utils):
        """测试agg_kernel方法，正常聚合数据"""
        input_df = pd.DataFrame({
            'Parent Module': ['p', 'p', 'p'],
            'Module': ['m', 'm', 'm'],
            'Op Name': ['op1', 'op1', 'op2'],
            'Kernel List': ['k1', 'k2', 'k3'],
            'Total Kernel Duration(ns)': [1000, 2000, 3000],
            'Avg Kernel Duration(ns)': [1000, 2000, 3000],
            'Op Count': [1, 1, 1]
        })
        result = CalibrateNpuGpu.agg_kernel(input_df)
        self.assertIn('Total Kernel Duration(us)', result.columns)
        self.assertIn('Avg Kernel Duration(us)', result.columns)
        self.assertEqual(result.loc[('p', 'm', 'op1'), 'Total Kernel Duration(us)'], 3.0)

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.ExcelUtils")
    def test_agg_kernel_with_missing_columns(self, mock_excel_utils):
        """测试agg_kernel方法，输入缺少列的DataFrame应抛出KeyError"""
        input_df = pd.DataFrame()
        with self.assertRaises(KeyError):
            CalibrateNpuGpu.agg_kernel(input_df)

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.PathManager.check_input_file_path")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.GPUAnalyzer")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.run")
    def test_run_success(self, mock_npu_run, mock_gpu_analyzer, mock_check_path):
        """测试run方法，成功执行分析流程"""
        mock_gpu_analyzer_instance = Mock()
        mock_gpu_df_dict = {0: pd.DataFrame({
            'Parent Module': ['p'],
            'Module': ['m'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(ns)': [1000],
            'Avg Kernel Duration(ns)': [1000],
            'Op Count': [1]
        })}
        mock_gpu_analyzer_instance.get_aggregated_df.return_value = mock_gpu_df_dict
        mock_gpu_analyzer.return_value = mock_gpu_analyzer_instance

        mock_npu_df_dict = [(0, pd.DataFrame({
            'Parent Module': ['p'],
            'Module': ['m'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(ns)': [1000],
            'Avg Kernel Duration(ns)': [1000],
            'Op Count': [1]
        }))]
        mock_npu_run.return_value = mock_npu_df_dict

        self.analysis._output_path = "/tmp"
        self.analysis.run(context=None)

        mock_gpu_analyzer_instance.get_aggregated_df.assert_called_once()
        mock_npu_run.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.PathManager.check_input_file_path")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.GPUAnalyzer")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.run")
    def test_run_when_gpu_analyze_failed_then_return(self, mock_npu_run, mock_gpu_analyzer, mock_check_path):
        """测试run方法，GPU分析失败时应返回"""
        mock_gpu_analyzer_instance = Mock()
        mock_gpu_analyzer_instance.get_aggregated_df.return_value = None
        mock_gpu_analyzer.return_value = mock_gpu_analyzer_instance

        self.analysis.run(context=None)
        mock_gpu_analyzer_instance.get_aggregated_df.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.PathManager.check_input_file_path")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.GPUAnalyzer")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.run")
    def test_run_when_npu_analyze_failed_then_return(self, mock_npu_run, mock_gpu_analyzer, mock_check_path):
        """测试run方法，NPU分析失败时应返回"""
        mock_gpu_analyzer_instance = Mock()
        mock_gpu_analyzer_instance.get_aggregated_df.return_value = {0: pd.DataFrame()}
        mock_gpu_analyzer.return_value = mock_gpu_analyzer_instance

        mock_npu_run.return_value = None

        self.analysis.run(context=None)
        mock_npu_run.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.logger")
    def test_save_db_when_df_is_none_then_warning(self, mock_logger):
        """测试save_db，df为None时应记录warning"""
        self.analysis.save_db(None, "test_table")
        mock_logger.warning.assert_called()

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.calibrate_npu_gpu.logger")
    def test_save_db_when_df_is_empty_then_warning(self, mock_logger):
        """测试save_db，df为空时应记录warning"""
        self.analysis.save_db(pd.DataFrame(), "test_table")
        mock_logger.warning.assert_called()


class TestGPUAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = GPUAnalyzer("/fake/gpu/path", "CalibrateNpuGpu")

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.GPUNVTXEventsExport")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.GPUKernelExport")
    def test_load_data_success(self, mock_kernel_export, mock_nvtx_export):
        """测试load_data方法，成功加载数据"""
        mock_nvtx_instance = Mock()
        mock_nvtx_instance.read_export_db.return_value = pd.DataFrame({
            'start': [1000], 'end': [2000], 'globalTid': [1], 'text': ['test']
        })
        mock_nvtx_export.return_value = mock_nvtx_instance

        mock_kernel_instance = Mock()
        mock_kernel_instance.read_export_db.return_value = pd.DataFrame({
            'cpu_start_ns': [1500], 'globalTid': [1], 'kernel_name': ['kernel1'],
            'gpu_duration_ns': [100], 'deviceId': [0]
        })
        mock_kernel_export.return_value = mock_kernel_instance

        df_nvtx, df_kernels = self.analyzer.load_data()
        self.assertIsNotNone(df_nvtx)
        self.assertIsNotNone(df_kernels)

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.logger")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.GPUNVTXEventsExport")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.GPUKernelExport")
    def test_load_data_when_nvtx_empty_then_error(self, mock_kernel_export, mock_nvtx_export, mock_logger):
        """测试load_data方法，nvtx数据为空时应记录error"""
        mock_nvtx_instance = Mock()
        mock_nvtx_instance.read_export_db.return_value = pd.DataFrame()
        mock_nvtx_export.return_value = mock_nvtx_instance

        mock_kernel_instance = Mock()
        mock_kernel_instance.read_export_db.return_value = pd.DataFrame()
        mock_kernel_export.return_value = mock_kernel_instance

        df_nvtx, df_kernels = self.analyzer.load_data()
        self.assertIsNone(df_nvtx)
        self.assertIsNone(df_kernels)

    def test_build_caches_normal(self):
        """测试_build_caches方法，正常构建缓存"""
        df_nvtx = pd.DataFrame({
            'name': ['Qwen::forward', 'Attention::forward', 'test_op', None]
        })
        user_def_markers = ['Qwen', 'Attention']

        marker_cache, op_cache = self.analyzer._build_caches(df_nvtx, user_def_markers)

        self.assertTrue(marker_cache['Qwen::forward'])
        self.assertTrue(marker_cache['Attention::forward'])
        self.assertFalse(marker_cache['test_op'])
        self.assertIsNone(op_cache['test_op'])

    def test_build_caches_with_default_markers(self):
        """测试_build_caches方法，使用默认user_def_markers会抛出TypeError"""
        df_nvtx = pd.DataFrame({
            'name': ['Qwen_forward', 'RandomOp', 'Attention_forward']
        })

        with self.assertRaises(TypeError):
            self.analyzer._build_caches(df_nvtx, None)

    def test_process_hierarchy_normal(self):
        """测试process_hierarchy方法，正常处理层级"""
        df_nvtx = pd.DataFrame({
            'start_ns': [1000, 2000],
            'end_ns': [1500, 2500],
            'thread_id': [1, 1],
            'name': ['Qwen_forward', 'Qwen_forward']
        })
        df_kernels = pd.DataFrame({
            'cpu_start_ns': [1200],
            'thread_id': [1],
            'kernel_name': ['kernel1'],
            'gpu_duration_ns': [100],
            'rank_id': [0]
        })

        result = self.analyzer.process_hierarchy(df_nvtx, df_kernels)
        self.assertIsNotNone(result)

    def test_process_hierarchy_with_custom_markers(self):
        """测试process_hierarchy方法，使用自定义markers"""
        df_nvtx = pd.DataFrame({
            'start_ns': [1000],
            'end_ns': [2000],
            'thread_id': [1],
            'name': ['CustomOp']
        })
        df_kernels = pd.DataFrame({
            'cpu_start_ns': [1500],
            'thread_id': [1],
            'kernel_name': ['kernel1'],
            'gpu_duration_ns': [100],
            'rank_id': [0]
        })

        result = self.analyzer.process_hierarchy(df_nvtx, df_kernels, user_def_markers=['CustomOp'])
        self.assertIsNotNone(result)

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.logger")
    def test_analyze_when_load_failed_then_error(self, mock_logger):
        """测试analyze方法，加载失败时应记录error"""
        mock_load_data = Mock(return_value=(None, None))
        self.analyzer.load_data = mock_load_data

        result = self.analyzer.analyze()
        self.assertIsNone(result)
        mock_logger.error.assert_called()

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.GPUNVTXEventsExport")
    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.gpu_analyzer.GPUKernelExport")
    def test_get_aggregated_df_success(self, mock_kernel_export, mock_nvtx_export):
        """测试get_aggregated_df方法，成功获取聚合数据"""
        mock_nvtx_instance = Mock()
        mock_nvtx_instance.read_export_db.return_value = pd.DataFrame({
            'start': [1000], 'end': [2000], 'globalTid': [1], 'text': ['Qwen_forward'], 'textId': [1]
        })
        mock_nvtx_export.return_value = mock_nvtx_instance

        mock_kernel_instance = Mock()
        mock_kernel_instance.read_export_db.return_value = pd.DataFrame({
            'start': [1500], 'globalTid': [1], 'kernel_name': ['kernel1'],
            'gpu_duration_ns': [100], 'deviceId': [0], 'correlationId': [1], 'demangledName': [1]
        })
        mock_kernel_export.return_value = mock_kernel_instance

        with self.assertRaises(AttributeError):
            self.analyzer.get_aggregated_df()


class TestComparator(unittest.TestCase):
    def setUp(self):
        self.df_gpu = pd.DataFrame({
            'Parent Module': ['p1', 'p2'],
            'Module': ['m1', 'm2'],
            'Op Name': ['op1', 'op2'],
            'Kernel List': ['k1', 'k2'],
            'Total Kernel Duration(us)': [10.0, 20.0],
            'Avg Kernel Duration(us)': [10.0, 20.0],
            'Op Count': [1, 1]
        })
        self.df_npu = pd.DataFrame({
            'Parent Module': ['p1', 'p2'],
            'Module': ['m1', 'm2'],
            'Op Name': ['op1', 'op2'],
            'Kernel List': ['k1', 'k2'],
            'Total Kernel Duration(us)': [15.0, 25.0],
            'Avg Kernel Duration(us)': [15.0, 25.0],
            'Op Count': [1, 1]
        })
        self.comparator = Comparator(self.df_gpu, self.df_npu)

    def test_get_best_fuzzy_match_normal(self):
        """测试get_best_fuzzy_match方法，正常匹配"""
        result = Comparator.get_best_fuzzy_match('test_op', ['test_op', 'other_op'], threshold=0.8)
        self.assertEqual(result, 'test_op')

    def test_get_best_fuzzy_match_no_candidates(self):
        """测试get_best_fuzzy_match方法，无候选时应返回None"""
        result = Comparator.get_best_fuzzy_match('test_op', [], threshold=0.8)
        self.assertIsNone(result)

    def test_get_best_fuzzy_match_below_threshold(self):
        """测试get_best_fuzzy_match方法，低于阈值时应返回None"""
        result = Comparator.get_best_fuzzy_match('xyz', ['abc', 'def'], threshold=0.8)
        self.assertIsNone(result)

    def test_compare_normal(self):
        """测试compare方法，正常比较"""
        result = self.comparator.compare(enable_fuzzy=False)

        self.assertIsNotNone(result)
        self.assertIn('(GPU) Total Kernel Duration(us)', result.columns)
        self.assertIn('(NPU) Total Kernel Duration(us)', result.columns)
        self.assertIn('(NPU/GPU) Module Time Ratio', result.columns)
        self.assertIn('(NPU-GPU,us) Module Time Diff', result.columns)

    def test_compare_with_fuzzy_enabled(self):
        """测试compare方法，启用模糊匹配"""
        result = self.comparator.compare(enable_fuzzy=True, fuzzy_threshold=0.8)

        self.assertIsNotNone(result)
        self.assertIn('Match Type', result.columns)

    def test_compare_when_gpu_empty(self):
        """测试compare方法，GPU数据为空时应能正常处理"""
        empty_df = pd.DataFrame({'Parent Module': [], 'Module': [], 'Op Name': [], 'Kernel List': [],
                               'Total Kernel Duration(us)': [], 'Avg Kernel Duration(us)': [], 'Op Count': []})
        comparator = Comparator(empty_df, self.df_npu)
        result = comparator.compare(enable_fuzzy=False)
        self.assertIsNotNone(result)

    def test_compare_when_npu_empty(self):
        """测试compare方法，NPU数据为空时应能正常处理"""
        empty_df = pd.DataFrame({'Parent Module': [], 'Module': [], 'Op Name': [], 'Kernel List': [],
                               'Total Kernel Duration(us)': [], 'Avg Kernel Duration(us)': [], 'Op Count': []})
        comparator = Comparator(self.df_gpu, empty_df)
        result = comparator.compare(enable_fuzzy=False)
        self.assertIsNotNone(result)

    def test_compare_calculate_ratio_correctly(self):
        """测试compare方法，计算比率正确"""
        df_gpu = pd.DataFrame({
            'Parent Module': ['p1'],
            'Module': ['m1'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(us)': [10.0],
            'Avg Kernel Duration(us)': [10.0],
            'Op Count': [1]
        })
        df_npu = pd.DataFrame({
            'Parent Module': ['p1'],
            'Module': ['m1'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(us)': [20.0],
            'Avg Kernel Duration(us)': [20.0],
            'Op Count': [1]
        })
        comparator = Comparator(df_gpu, df_npu)
        result = comparator.compare(enable_fuzzy=False)

        ratio_value = result['(NPU/GPU) Module Time Ratio'].iloc[0]
        self.assertNotEqual(ratio_value.strip(), ' ')

    def test_compare_calculate_diff_correctly(self):
        """测试compare方法，计算差值正确"""
        df_gpu = pd.DataFrame({
            'Parent Module': ['p1'],
            'Module': ['m1'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(us)': [10.0],
            'Avg Kernel Duration(us)': [10.0],
            'Op Count': [1]
        })
        df_npu = pd.DataFrame({
            'Parent Module': ['p1'],
            'Module': ['m1'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(us)': [20.0],
            'Avg Kernel Duration(us)': [20.0],
            'Op Count': [1]
        })
        comparator = Comparator(df_gpu, df_npu)
        result = comparator.compare(enable_fuzzy=False)

        diff_value = result['(NPU-GPU,us) Module Time Diff'].iloc[0]
        self.assertEqual(float(diff_value), 10.0)

    def test_compare_percentage_format(self):
        """测试compare方法，百分比格式化正确"""
        result = self.comparator.compare(enable_fuzzy=False)

        gpu_percent_col = '(GPU) Total Kernel Duration(%)'
        npu_percent_col = '(NPU) Total Kernel Duration(%)'

        for val in result[gpu_percent_col]:
            if val.strip():
                self.assertRegex(val, r'\d+\.\d+%')

        for val in result[npu_percent_col]:
            if val.strip():
                self.assertRegex(val, r'\d+\.\d+%')

    @patch("msprof_analyze.cluster_analyse.recipes.calibrate_npu_gpu.comparator.logger")
    def test_compare_with_ascend_replacement(self, mock_logger):
        """测试compare方法，Ascend字符串替换正确"""
        df_gpu = pd.DataFrame({
            'Parent Module': ['p1'],
            'Module': ['m1'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(us)': [10.0],
            'Avg Kernel Duration(us)': [10.0],
            'Op Count': [1]
        })
        df_npu = pd.DataFrame({
            'Parent Module': ['Ascend/p1'],
            'Module': ['m1'],
            'Op Name': ['op1'],
            'Kernel List': ['k1'],
            'Total Kernel Duration(us)': [10.0],
            'Avg Kernel Duration(us)': [10.0],
            'Op Count': [1]
        })
        comparator = Comparator(df_gpu, df_npu)
        result = comparator.compare(enable_fuzzy=False)

        self.assertIsNotNone(result)