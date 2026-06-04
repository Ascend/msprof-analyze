# Copyright (c) 2025, Huawei Technologies Co., Ltd. All rights reserved.
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
# pylint: disable=no-member

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from msprof_analyze.advisor.config.config import Config


class TestConfig(unittest.TestCase):
    # pylint: disable=consider-using-with
    def setUp(self):
        Config.reset_all_instances()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        Config.reset_all_instances()
        self.temp_dir.cleanup()

    # pylint: enable=consider-using-with

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_config_init_initializes_reader(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "result.txt"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        self.assertIsNotNone(config.config_reader)

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_config_init_checks_required_sections(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "result.txt"
        mock_reader.get_config.return_value = mock_cfg

        Config()
        mock_reader.validate.assert_called_once()

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_set_config_and_get_config(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "result.txt"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        config.set_config("test_key", "test_value")
        self.assertEqual(config.get_config("test_key"), "test_value")

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_get_config_returns_empty_for_missing_key(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "result.txt"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        result = config.get_config("nonexistent_key")
        self.assertEqual(result, "")

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    @patch('msprof_analyze.advisor.config.config.PathManager.make_dir_safety')
    def test_set_log_path_creates_directory(self, mock_make_dir, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "result.txt"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        log_dir = os.path.join(self.temp_dir.name, "log")
        config.set_log_path("result.txt", log_path=log_dir)
        mock_make_dir.assert_called_once_with(log_dir)

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_operator_bound_ratio_returns_float(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "0.85"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        ratio = config.operator_bound_ratio
        self.assertIsInstance(ratio, float)
        self.assertEqual(ratio, 0.85)

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_frequency_threshold_returns_float(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "0.5"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        threshold = config.frequency_threshold
        self.assertIsInstance(threshold, float)

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_url_property_returns_empty_on_exception(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()

        def get_side_effect(section, key):
            if section == "ANALYSE":
                return "result.txt"
            if section == "URL":
                raise ValueError("config error")
            return "default"

        mock_cfg.get.side_effect = get_side_effect
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        url = config.timeline_api_doc_url
        self.assertEqual(url, "")

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_ascend_profiler_url_returns_empty_on_exception(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()

        def get_side_effect(section, key):
            if section == "ANALYSE":
                return "result.txt"
            if section == "URL":
                raise ValueError("config error")
            return "default"

        mock_cfg.get.side_effect = get_side_effect
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        url = config.ascend_profiler_url
        self.assertEqual(url, "")

    @patch('msprof_analyze.advisor.config.config.SafeConfigReader')
    def test_remove_log_removes_empty_dir(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "result.txt"
        mock_reader.get_config.return_value = mock_cfg

        config = Config()
        config.log_path = self.temp_dir.name
        config.remove_log()
        self.assertFalse(os.path.isdir(self.temp_dir.name))
