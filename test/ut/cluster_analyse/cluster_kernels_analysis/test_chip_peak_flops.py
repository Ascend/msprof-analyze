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

import os
import json
import tempfile
import unittest
from unittest.mock import patch

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.chip_peak_flops import ChipPeakFLOPSCalculator
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.operator_flops import DataType
from msprof_analyze.prof_common.constant import Constant


class TestChipPeakFLOPSCalculator(unittest.TestCase):
    def create_profiler_dir_with_info(self, base_dir, ai_core_num=1, aic_frequency="1000"):
        profiler_dir = os.path.join(base_dir, "profiler")
        os.makedirs(profiler_dir, exist_ok=True)
        device_dir = os.path.join(profiler_dir, "device_0")
        os.makedirs(device_dir, exist_ok=True)

        info_path = os.path.join(device_dir, "info.json.0")
        content = {
            "DeviceInfo": [
                {
                    "ai_core_num": ai_core_num,
                    "aic_frequency": aic_frequency,
                }
            ]
        }

        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(content, f)
        return profiler_dir

    def test___init___when_profiler_path_not_exist_then_log_error_and_invalid(self):
        invalid_path = "path_not_exist_12345"
        calc = ChipPeakFLOPSCalculator(invalid_path)
        self.assertFalse(calc.is_valid())

    def test_is_valid_when_chip_info_loaded_then_return_true(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profiler_dir = self.create_profiler_dir_with_info(tmp_dir)
            calc = ChipPeakFLOPSCalculator(profiler_dir)
            self.assertTrue(calc.is_valid())

    def test_is_valid_when_chip_info_invalid_then_return_false(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profiler_dir = self.create_profiler_dir_with_info(tmp_dir, ai_core_num=0, aic_frequency="0")
            calc = ChipPeakFLOPSCalculator(profiler_dir)
            self.assertFalse(calc.is_valid())

    def test_find_device_info_json_when_file_exists_then_return_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profiler_dir = self.create_profiler_dir_with_info(tmp_dir)
            result = ChipPeakFLOPSCalculator.find_device_info_json(profiler_dir)
            self.assertTrue(os.path.isfile(result))

    def test_find_device_info_json_when_file_not_exist_then_raise_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                ChipPeakFLOPSCalculator.find_device_info_json(tmp_dir)

    def test_get_peak_performance_when_invalid_device_info_then_return_invalid(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profiler_dir = self.create_profiler_dir_with_info(tmp_dir, ai_core_num=0, aic_frequency="0")
            calc = ChipPeakFLOPSCalculator(profiler_dir)
            result = calc.get_peak_performance(DataType.FLOAT16)
            self.assertEqual(result, Constant.INVALID_RETURN)

    def test_get_peak_performance_when_valid_input_then_return_expected_flops(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profiler_dir = self.create_profiler_dir_with_info(tmp_dir, ai_core_num=2, aic_frequency="1000")
            calc = ChipPeakFLOPSCalculator(profiler_dir)
            result = calc.get_peak_performance(DataType.FLOAT16)
            ops_per_cycle = ChipPeakFLOPSCalculator.OPS_PER_CYCLE[DataType.FLOAT16]
            expected = 2 * 1000 * ops_per_cycle * ChipPeakFLOPSCalculator.MHZ_TO_HZ
            self.assertEqual(result, expected)

    def test_get_peak_performance_when_called_twice_then_use_cached_value(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            profiler_dir = self.create_profiler_dir_with_info(tmp_dir, ai_core_num=2, aic_frequency="1000")
            calc = ChipPeakFLOPSCalculator(profiler_dir)
            with patch.object(ChipPeakFLOPSCalculator, "_load_chip_info", wraps=calc._load_chip_info) as mock_load:
                first = calc.get_peak_performance(DataType.FLOAT16)
                second = calc.get_peak_performance(DataType.FLOAT16)
                self.assertEqual(first, second)
                # peak_flops should already contain cached value after first call
                self.assertIn(DataType.FLOAT16, calc.peak_flops)
                self.assertEqual(mock_load.call_count, 0)
