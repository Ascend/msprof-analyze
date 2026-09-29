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
from unittest.mock import patch

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor import MsprofDataPreprocessor

NAMESPACE = 'msprof_analyze.cluster_analyse.cluster_data_preprocess'


class TestMsprofDataPreprocessor(unittest.TestCase):

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_msprof_data_preprocessor")
        os.makedirs(self.test_dir, exist_ok=True)
        self.path_list = [os.path.join(self.test_dir, "PROF_12450"),
                          os.path.join(self.test_dir, "PROF_114514")]

        for path in self.path_list:
            os.makedirs(path, exist_ok=True)
            os.makedirs(os.path.join(path, "device_0"), exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('os.listdir')
    def test_get_msprof_profiler_db_path_will_return_latest_profile_db_path_when_input_dir_valid(self, mock_listdir):
        mock_listdir.return_value = [
            "msprof_20250101120000.db",
            "msprof_20250101120001.db",
            "other_file.txt",
            "msprof_20250101120002.db"
        ]

        result = MsprofDataPreprocessor.get_msprof_profiler_db_path("/test/path")

        expected_path = os.path.join("/test/path", "msprof_20250101120002.db")
        self.assertEqual(result, expected_path)

    @patch('os.listdir')
    def test_get_msprof_profiler_db_path_will_return_empty_when_input_with_no_valid_files(self, mock_listdir):
        mock_listdir.return_value = ["other_file.txt", "not_msprof.db"]

        result = MsprofDataPreprocessor.get_msprof_profiler_db_path("/test/path")

        self.assertEqual(result, "")

    @patch('os.listdir')
    def test_get_device_id_with_return_first_matched_device_id_when_input_valid_device_file_list(self, mock_listdir):
        mock_listdir.return_value = ["device_0", "device_1", "other_device"]

        result = MsprofDataPreprocessor.get_device_id("/test/path")

        # Should return the first matched device id
        self.assertEqual(result, 0)

    @patch('os.listdir')
    def test_get_device_id_with_return_none_when_input_file_list_invalid(self, mock_listdir):
        mock_listdir.return_value = ["other_file", "not_device"]

        result = MsprofDataPreprocessor.get_device_id("/test/path")

        self.assertIsNone(result)

    @patch('os.listdir')
    def test_find_info_json_file_with_valid_file_should_return_correct_answer(self, mock_listdir):
        # Mock the directory structure
        test_path = "/test/path"

        def mock_listdir_side_effect(path):
            if path == os.path.join(test_path, "PROF_12450"):
                return ["invalid_file", "device_0"]
            if path == os.path.join(test_path, "PROF_12450", "device_0"):
                return ["invalid_file", "info.json.0"]
            return []

        mock_listdir.side_effect = mock_listdir_side_effect

        preprocessor = MsprofDataPreprocessor([self.test_dir])

        file_path = os.path.join(test_path, "PROF_12450")
        with patch('os.path.isdir',
                   side_effect=lambda args: True if args == os.path.join(file_path, "device_0") else False):
            result = preprocessor._find_info_json_file(file_path)

        expected_path = os.path.join("/test/path", "PROF_12450", "device_0", "info.json.0")
        self.assertEqual(result, expected_path)

    @patch('os.listdir')
    def test_find_info_json_file_will_return_none_when_no_valid_file(self, mock_listdir):
        mock_listdir.return_value = ["info.json"]

        preprocessor = MsprofDataPreprocessor(self.path_list)
        result = preprocessor._find_info_json_file("/test/path")

        self.assertIsNone(result)

    def test_get_data_type_with_single_type_should_pop_data_type(self):
        preprocessor = MsprofDataPreprocessor(self.path_list)
        preprocessor.data_type.add(Constant.DB)

        result = preprocessor.get_data_type()

        self.assertEqual(result, Constant.DB)
        self.assertEqual(len(preprocessor.data_type), 0)  # Should be popped

    def test_get_data_type_with_multiple_types_should_return_constant_invalid(self):
        preprocessor = MsprofDataPreprocessor(self.path_list)
        preprocessor.data_type.add(Constant.DB)
        preprocessor.data_type.add(Constant.TEXT)

        result = preprocessor.get_data_type()

        self.assertEqual(result, Constant.INVALID)

    def test_get_data_type_with_empty_set_should_return_constant_invalid(self):
        preprocessor = MsprofDataPreprocessor(self.path_list)

        result = preprocessor.get_data_type()

        self.assertEqual(result, Constant.INVALID)

    def test_get_data_map_should_log_error_when_prof_data_not_parsed_fully(self):
        with patch('os.listdir') as mock_listdir, \
             patch(NAMESPACE + '.msprof_data_preprocessor.logger'), \
             patch(NAMESPACE + '.msprof_data_preprocessor.FileManager') as mock_file_manager:

            mock_info_json = {"rank_id": 0, "hostUid": "9953303134705188359"}
            mock_file_manager.read_json_file.return_value = mock_info_json

            # Mock directory structure
            def mock_listdir_side_effect(path):
                if path == os.path.join(self.test_dir, "PROF_12450"):
                    return ["invalid_file", "device_0"]
                if path == os.path.join(self.test_dir, "PROF_12450", "device_0"):
                    return ["invalid_file", "info.json.0"]
                return []

            mock_listdir.side_effect = mock_listdir_side_effect

            preprocessor = MsprofDataPreprocessor(self.path_list)
            result = preprocessor.get_data_map()

            self.assertEqual({}, result)

    def test_get_data_map_should_return_data_map_when_run_success(self):
        with patch('os.path.exists', return_value=True), \
             patch('os.listdir') as mock_listdir, \
             patch(NAMESPACE + '.msprof_data_preprocessor.logger'), \
             patch(NAMESPACE + '.msprof_data_preprocessor.FileManager') as mock_file_manager:
            # Mock info.json content with rank_id
            mock_info_json = {"rank_id": 0, "hostUid": "9953303134705188359"}
            mock_file_manager.read_json_file.return_value = mock_info_json

            # Mock directory structure
            def mock_listdir_side_effect(path):
                if path == os.path.join(self.test_dir, "PROF_12450"):
                    return ["invalid_file", "device_0"]
                if path == os.path.join(self.test_dir, "PROF_12450", "device_0"):
                    return ["invalid_file", "info.json.0"]
                return []

            mock_listdir.side_effect = mock_listdir_side_effect

            preprocessor = MsprofDataPreprocessor(self.path_list)
            result = preprocessor.get_data_map()

            self.assertEqual(os.path.join(self.test_dir, "PROF_12450"), result[0])


    @patch('msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor.logger')
    @patch('os.listdir')
    def test_get_data_map_with_no_info_json(self, mock_listdir, mock_logger):
        mock_listdir.return_value = ["other_file.txt"]

        preprocessor = MsprofDataPreprocessor(self.path_list)
        result = preprocessor.get_data_map()

        # Should log error and return empty dict
        mock_logger.error.assert_called()
        self.assertEqual(result, {})


    @patch('msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor.logger')
    @patch('os.path.exists')
    @patch('os.listdir')
    def test_get_data_map_with_incomplete_text_data_should_log_error_and_return_empty_map(self,
                                                                                          mock_listdir,
                                                                                          mock_exists, mock_logger):
        def mock_listdir_side_effect(path):
            if "test_path1" in path:
                return ["device_0"]
            elif "device_0" in path:
                return ["info.json.0"]
            return []

        def mock_exists_side_effect(path):
            if "mindstudio_profiler_output" in path:
                return True
            elif "analyze" in path:
                return False
            return False

        mock_listdir.side_effect = mock_listdir_side_effect
        mock_exists.side_effect = mock_exists_side_effect

        preprocessor = MsprofDataPreprocessor(self.path_list)
        result = preprocessor.get_data_map()

        mock_logger.error.assert_called()
        self.assertEqual(result, {})

    @patch('msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor.logger')
    @patch('os.path.exists')
    @patch('os.listdir')
    def test_get_data_map_with_no_profiler_output_should_log_error_and_return_empty_map(self,
                                                                                         mock_listdir,
                                                                                         mock_exists, mock_logger):
        def mock_listdir_side_effect(path):
            if "test_path1" in path:
                return ["device_0"]
            elif "device_0" in path:
                return ["info.json.0"]
            return []

        mock_listdir.side_effect = mock_listdir_side_effect
        mock_exists.return_value = False

        preprocessor = MsprofDataPreprocessor(self.path_list)
        result = preprocessor.get_data_map()

        mock_logger.error.assert_called()
        self.assertEqual(result, {})

    def test_get_data_map_empty_path_list_should_return_empty_map(self):
        preprocessor = MsprofDataPreprocessor([])
        result = preprocessor.get_data_map()

        self.assertEqual(result, {})


if __name__ == '__main__':
    unittest.main()
