# Copyright (c) 2026, Huawei Technologies Co., Ltd. All rights reserved.
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

from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import (
    CsvTitle,
    CsvTitleV1,
    CsvTitleV2,
    Constant,
    CoreType,
    PerfColor,
)


class TestCsvTitle(unittest.TestCase):
    def test_csv_title_has_model_name(self):
        self.assertEqual(CsvTitle.MODEL_NAME, "Model Name")

    def test_csv_title_has_task_id(self):
        self.assertEqual(CsvTitle.TASK_ID, "Task ID")

    def test_csv_title_has_aicore_time(self):
        self.assertEqual(CsvTitle.AICORE_TIME, "aicore_time(us)")

    def test_csv_title_has_cube_utilization(self):
        self.assertIn("cube_utilization", CsvTitle.CUBE_UTILIZATION)


class TestCsvTitleV1(unittest.TestCase):
    def test_inherits_from_csv_title(self):
        self.assertTrue(issubclass(CsvTitleV1, CsvTitle))

    def test_has_v1_specific_fields(self):
        self.assertTrue(hasattr(CsvTitleV1, 'OP_NAME'))


class TestCsvTitleV2(unittest.TestCase):
    def test_inherits_from_csv_title(self):
        self.assertTrue(issubclass(CsvTitleV2, CsvTitle))

    def test_has_v2_specific_fields(self):
        self.assertTrue(hasattr(CsvTitleV2, 'OP_NAME'))


class TestConstant(unittest.TestCase):
    def test_npu_fused_is_defined(self):
        self.assertIsNotNone(Constant.NPU_FUSED)

    def test_npu_slow_is_defined(self):
        self.assertIsNotNone(Constant.NPU_SLOW)

    def test_pt_prof_suffix_is_ascend_pt(self):
        self.assertEqual(Constant.PT_PROF_SUFFIX, "ascend_pt")

    def test_update_title_is_callable(self):
        self.assertTrue(callable(Constant.update_title))


class TestCoreType(unittest.TestCase):
    def test_aic_is_defined(self):
        self.assertTrue(hasattr(CoreType, 'AIC'))

    def test_aiv_is_defined(self):
        self.assertTrue(hasattr(CoreType, 'AIV'))

    def test_aicpu_is_defined(self):
        self.assertTrue(hasattr(CoreType, 'AICPU'))


class TestPerfColor(unittest.TestCase):
    def test_white_is_0(self):
        self.assertEqual(PerfColor.WHITE.value, 0)

    def test_green_is_1(self):
        self.assertEqual(PerfColor.GREEN.value, 1)
