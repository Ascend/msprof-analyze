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

import unittest
import os
import shutil
import stat
import json
from unittest.mock import patch, MagicMock

from msprof_analyze.advisor.dataset.ai_core_freq.ai_core_freq_dataset import AICoreFreqDataset


class TestAICoreFreqDataset(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"

    @classmethod
    def create_trace_view_json(cls):
        trace_view_data = [
            {
                "name": "ProfilerStep#1",
                "ts": "1000",
                "dur": "100",
                "args": {}
            },
            {
                "name": "Matmul",
                "ts": "1100",
                "dur": "50",
                "args": {"Task Type": "AI_CORE"}
            },
            {
                "name": "AI Core Freq",
                "ts": "1000",
                "args": {"MHz": "1000"}
            },
            {
                "name": "Conv2D",
                "ts": "1200",
                "dur": "100",
                "args": {"Task Type": "AI_CORE"}
            },
            {
                "name": "AI Core Freq",
                "ts": "1250",
                "args": {"MHz": "800"}
            }
        ]

        with os.fdopen(os.open(f"{TestAICoreFreqDataset.OUTPUT_DIR}/trace_view.json",
                              os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(trace_view_data))

    def setUp(self):
        if os.path.exists(TestAICoreFreqDataset.TMP_DIR):
            shutil.rmtree(TestAICoreFreqDataset.TMP_DIR)
        if not os.path.exists(TestAICoreFreqDataset.TMP_DIR):
            os.makedirs(TestAICoreFreqDataset.TMP_DIR)
        if not os.path.exists(TestAICoreFreqDataset.OUTPUT_DIR):
            os.makedirs(TestAICoreFreqDataset.OUTPUT_DIR)

    def tearDown(self):
        if os.path.exists(TestAICoreFreqDataset.TMP_DIR):
            shutil.rmtree(TestAICoreFreqDataset.TMP_DIR)

    @patch('msprof_analyze.advisor.dataset.ai_core_freq.ai_core_freq_dataset.Config')
    def test_aicire_freq_dataset(self, mock_config_class):
        # Mock Config singleton instance
        mock_config_instance = MagicMock()
        mock_config_class.return_value = mock_config_instance
        mock_config_instance.get_config.return_value = True

        self.create_trace_view_json()
        data = {}
        dataset = AICoreFreqDataset(self.OUTPUT_DIR, data)

        # Verify initialization
        self.assertEqual(dataset.timeline_dir, self.OUTPUT_DIR)
        self.assertEqual(len(dataset.profiler_step), 1)
        self.assertEqual(len(dataset.ai_core_ops), 2)  # Now we have 2 operators
        self.assertEqual(len(dataset.ai_core_freq), 2)  # Now we have 2 frequency events
        self.assertEqual(dataset.get_key(), "ai_core_freq_dataset")

        # Verify op_freq data
        self.assertIn("Matmul", dataset.op_freq)
        self.assertIn("Conv2D", dataset.op_freq)

        # Verify Matmul frequency info
        matmul_freq = dataset.op_freq["Matmul"]
        self.assertEqual(matmul_freq["count"], 1)
        self.assertEqual(matmul_freq["dur"], 50.0)
        self.assertEqual(len(matmul_freq["freq_list"]), 1)
        self.assertEqual(matmul_freq["freq_list"][0], 1000.0)

        # Verify Conv2D frequency info
        conv2d_freq = dataset.op_freq["Conv2D"]
        self.assertEqual(conv2d_freq["count"], 1)
        self.assertEqual(conv2d_freq["dur"], 100.0)
        self.assertEqual(len(conv2d_freq["freq_list"]), 1)
        self.assertEqual(conv2d_freq["freq_list"][0], 800.0)
