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
import shutil
import unittest
from unittest.mock import patch, Mock
from collections import defaultdict

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_data_preprocess.prof_data_allocate import ProfDataAllocate


NAMESPACE = "msprof_analyze.cluster_analyse.cluster_data_preprocess.prof_data_allocate."


class TestProfDataAllocate(unittest.TestCase):
    """Test cases for ProfDataAllocate class"""
    
    TEST_DIR = os.path.join(os.path.dirname(__file__), 'TEST_PROF_DATA_ALLOCATE')
    
    def setUp(self):
        """Set up test environment"""
        if os.path.exists(self.TEST_DIR):
            shutil.rmtree(self.TEST_DIR)
        os.makedirs(self.TEST_DIR)
        
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.TEST_DIR):
            shutil.rmtree(self.TEST_DIR)
    
    def test_init_when_given_profiling_path_then_initialize_correctly(self):
        """Test initialization with profiling path"""
        profiling_path = "/test/path"
        allocator = ProfDataAllocate(profiling_path)
        
        self.assertEqual(allocator.profiling_path, profiling_path)
        self.assertEqual(allocator.data_type, "")
        self.assertEqual(allocator.data_map, {})
        self.assertEqual(allocator.prof_type, "")
        self.assertEqual(allocator._msmonitor_data_map, {})
    
    def test_match_file_pattern_in_dir_when_file_exists_then_return_filename(self):
        """Test matching file pattern when file exists"""
        test_dir = os.path.join(self.TEST_DIR, "test_dir")
        os.makedirs(test_dir)
        
        # Create test file
        test_file = os.path.join(test_dir, "ascend_pytorch_profiler_1.db")
        with open(test_file, 'w') as f:
            f.write("test")
        
        pattern = ProfDataAllocate.DB_PATTERNS[Constant.PYTORCH]
        result = ProfDataAllocate.match_file_pattern_in_dir(test_dir, pattern)
        
        self.assertEqual(result, "ascend_pytorch_profiler_1.db")
    
    def test_match_file_pattern_in_dir_when_file_not_exists_then_return_empty_string(self):
        """Test matching file pattern when file doesn't exist"""
        test_dir = os.path.join(self.TEST_DIR, "test_dir")
        os.makedirs(test_dir)
        
        pattern = ProfDataAllocate.DB_PATTERNS[Constant.PYTORCH]
        result = ProfDataAllocate.match_file_pattern_in_dir(test_dir, pattern)
        
        self.assertEqual(result, "")

    def test_extract_rank_id_from_profiler_db_when_pytorch_file_then_return_rank_id(self):
        """Test extracting rank ID from PyTorch profiler DB filename"""
        file_name = "ascend_pytorch_profiler_1.db"
        prof_type = Constant.PYTORCH
        
        result = ProfDataAllocate._extract_rank_id_from_profiler_db(file_name, prof_type)
        
        self.assertEqual(result, 1)
    
    def test_extract_rank_id_from_profiler_db_when_mindspore_file_then_return_rank_id(self):
        """Test extracting rank ID from MindSpore profiler DB filename"""
        file_name = "ascend_mindspore_profiler_2.db"
        prof_type = Constant.MINDSPORE
        
        result = ProfDataAllocate._extract_rank_id_from_profiler_db(file_name, prof_type)
        
        self.assertEqual(result, 2)
    
    def test_extract_rank_id_from_profiler_db_when_msmonitor_file_then_return_rank_id(self):
        """Test extracting rank ID from MSMonitor profiler DB filename"""
        file_name = "msmonitor_1234567_20250101120000000_1.db"
        prof_type = Constant.MSMONITOR
        
        result = ProfDataAllocate._extract_rank_id_from_profiler_db(file_name, prof_type)
        
        self.assertEqual(result, 1)

    def test_extract_rank_id_from_profiler_db_when_invalid_format_then_return_none(self):
        """Test extracting rank ID from invalid filename format"""
        file_name = "invalid_filename.db"
        prof_type = Constant.PYTORCH

        result = ProfDataAllocate._extract_rank_id_from_profiler_db(file_name, prof_type)

        self.assertIsNone(result)

    def test_extract_rank_id_from_profiler_db_when_no_rank_id_then_return_minus_one(self):
        """Test extracting rank ID from invalid filename format"""
        file_name = "ascend_pytorch_profiler.db"
        prof_type = Constant.PYTORCH
        
        result = ProfDataAllocate._extract_rank_id_from_profiler_db(file_name, prof_type)
        
        self.assertEqual(result, -1)
    
    def test_extract_rank_id_from_profiler_db_when_unsupported_prof_type_then_return_none(self):
        """Test extracting rank ID from unsupported profiler type"""
        file_name = "test.db"
        prof_type = "unsupported"
        
        result = ProfDataAllocate._extract_rank_id_from_profiler_db(file_name, prof_type)
        
        self.assertIsNone(result)
    
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_db_prof_data')
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_text_prof_data')
    def test_allocate_prof_data_when_db_allocation_succeeds_then_return_true(self, mock_text_alloc, mock_db_alloc):
        """Test prof data allocation when DB allocation succeeds"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        mock_db_alloc.return_value = True
        allocator.prof_type = Constant.PYTORCH
        
        result = allocator.allocate_prof_data()
        
        self.assertTrue(result)
        mock_db_alloc.assert_called_once()
        mock_text_alloc.assert_not_called()
    
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_db_prof_data')
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_text_prof_data')
    def test_allocate_prof_data_when_db_fails_text_succeeds_then_return_true(self, mock_text_alloc, mock_db_alloc):
        """Test prof data allocation when DB fails but text allocation succeeds"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        mock_db_alloc.return_value = False
        mock_text_alloc.return_value = True
        
        result = allocator.allocate_prof_data()
        
        self.assertTrue(result)
        mock_db_alloc.assert_called_once()
        mock_text_alloc.assert_called_once()
    
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_db_prof_data')
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_text_prof_data')
    def test_allocate_prof_data_when_both_fail_then_return_false(self, mock_text_alloc, mock_db_alloc):
        """Test prof data allocation when both DB and text allocation fail"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        mock_db_alloc.return_value = False
        mock_text_alloc.return_value = False
        allocator._msmonitor_data_map = {}
        
        result = allocator.allocate_prof_data()
        
        self.assertFalse(result)
        mock_db_alloc.assert_called_once()
        mock_text_alloc.assert_called_once()
    
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_db_prof_data')
    @patch(NAMESPACE + 'ProfDataAllocate.allocate_text_prof_data')
    def test_allocate_prof_data_when_msmonitor_data_exists_then_return_true(self, mock_text_alloc, mock_db_alloc):
        """Test prof data allocation when MSMonitor data exists"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        mock_db_alloc.return_value = False
        mock_text_alloc.return_value = False
        allocator._msmonitor_data_map = {1: ["/path/to/file.db"]}
        
        result = allocator.allocate_prof_data()
        
        self.assertTrue(result)
        self.assertEqual(allocator.prof_type, Constant.MSMONITOR)
        self.assertEqual(allocator.data_type, Constant.DB)
        self.assertEqual(allocator.data_map, {1: ["/path/to/file.db"]})

    @patch('msprof_analyze.prof_common.path_manager.PathManager.limited_depth_walk')
    @patch(NAMESPACE + 'ProfDataAllocate.match_file_pattern_in_dir')
    def test_allocate_db_prof_data_when_pytorch_data_exists_then_return_true(self, mock_match_file, mock_walk):
        """Test DB prof data allocation when PyTorch data exists"""
        # Mock directory structure
        mock_walk.return_value = [
            (self.TEST_DIR, ["ASCEND_PROFILER_OUTPUT"], []),
            (os.path.join(self.TEST_DIR, "ASCEND_PROFILER_OUTPUT"), [], ["ascend_pytorch_profiler_1.db"])
        ]
        mock_match_file.side_effect = ["ascend_pytorch_profiler_1.db", ""]
        
        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_db_prof_data()
        
        self.assertTrue(result)
        self.assertEqual(allocator.prof_type, Constant.PYTORCH)
        self.assertEqual(allocator.data_type, Constant.DB)

    def test_allocate_db_prof_data_when_only_analysis_db_exists_then_return_true(self):
        rank_root = os.path.join(self.TEST_DIR, "worker_0_20260101120000_ascend_pt")
        profiler_output = os.path.join(rank_root, Constant.ASCEND_PROFILER_OUTPUT)
        os.makedirs(profiler_output)
        with open(os.path.join(rank_root, "profiler_info_3.json"), 'w') as f:
            f.write("profiler_info")
        with open(os.path.join(profiler_output, "analysis.db"), 'w') as f:
            f.write("analysis")

        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_db_prof_data()

        self.assertTrue(result)
        self.assertEqual(allocator.prof_type, Constant.PYTORCH)
        self.assertEqual(allocator.data_type, Constant.DB)
        self.assertEqual(allocator.data_map, {3: rank_root})
    
    @patch('msprof_analyze.prof_common.path_manager.PathManager.limited_depth_walk')
    @patch(NAMESPACE + 'ProfDataAllocate.match_file_pattern_in_dir')
    def test_allocate_db_prof_data_when_msmonitor_data_exists_then_return_true(self, mock_match_file, mock_walk):
        """Test DB prof data allocation when MSMonitor data exists"""
        # Mock directory structure
        mock_walk.return_value = [
            (self.TEST_DIR, [], ["msmonitor_1234567_20250101120000000_1.db"])
        ]
        mock_match_file.return_value = "msmonitor_1234567_20250101120000000_1.db"
        
        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_db_prof_data()
        
        self.assertTrue(result)
        self.assertIn(1, allocator._msmonitor_data_map)


    @patch('msprof_analyze.prof_common.path_manager.PathManager.limited_depth_walk')
    @patch(NAMESPACE + 'ProfDataAllocate.match_file_pattern_in_dir')
    def test_allocate_db_prof_data_when_both_pytorch_and_mindspore_then_recognize_pytorch(self, mock_match_file, mock_walk):
        """Test DB prof data allocation when both PyTorch and MindSpore data exist"""
        # Mock directory structure with both types
        mock_walk.return_value = [
            (self.TEST_DIR, ["ASCEND_PROFILER_OUTPUT"], []),
            (os.path.join(self.TEST_DIR, "ASCEND_PROFILER_OUTPUT"), [], ["ascend_pytorch_profiler_1.db",
                                                                         "ascend_mindspore_profiler_2.db"])
        ]
        mock_match_file.side_effect = ["ascend_pytorch_profiler_1.db", "ascend_mindspore_profiler_2.db"]

        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_db_prof_data()

        self.assertTrue(result)
        self.assertEqual(allocator.prof_type, Constant.PYTORCH)
    
    @patch('msprof_analyze.prof_common.path_manager.PathManager.limited_depth_walk')
    def test_allocate_db_prof_data_when_no_data_exists_then_return_false(self, mock_walk):
        """Test DB prof data allocation when no data exists"""
        mock_walk.return_value = [(self.TEST_DIR, [], [])]
        
        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_db_prof_data()
        
        self.assertFalse(result)
    
    def test_allocate_text_prof_data_when_pytorch_text_data_exists_then_return_true(self):
        """Test text prof data allocation when PyTorch text data exists"""
        pytorch_dir = os.path.join(self.TEST_DIR, "test_ascend_pt")
        os.makedirs(pytorch_dir)
        os.makedirs(os.path.join(pytorch_dir, Constant.ASCEND_PROFILER_OUTPUT))
        profiler_info = os.path.join(pytorch_dir, "profiler_info_1.json")
        with open(profiler_info, 'w') as f:
            f.write("profiler_info")

        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_text_prof_data()

        self.assertTrue(result)
        self.assertEqual(allocator.prof_type, Constant.PYTORCH)
        self.assertEqual(allocator.data_type, Constant.TEXT)

    def test_allocate_text_prof_data_when_both_pytorch_and_mindspore_text_exist_then_return_false(self,):
        """Test text prof data allocation when both PyTorch and MindSpore text data exist"""
        pytorch_dir = os.path.join(self.TEST_DIR, "test_ascend_pt")
        mindspore_dir = os.path.join(self.TEST_DIR, "test_ascend_ms")
        dir_list = [pytorch_dir, os.path.join(pytorch_dir, Constant.ASCEND_PROFILER_OUTPUT),
                    mindspore_dir, os.path.join(mindspore_dir, Constant.ASCEND_PROFILER_OUTPUT)]
        for path in dir_list:
            os.makedirs(path)
        profiler_info_list = [os.path.join(pytorch_dir, "profiler_info_1.json"),
                              os.path.join(mindspore_dir, "profiler_info_0.json")]
        for profiler_info in profiler_info_list:
            with open(profiler_info, 'w') as f:
                f.write("profiler_info")
        
        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_text_prof_data()
        
        self.assertFalse(result)
        self.assertEqual(allocator.prof_type, Constant.INVALID)
    
    @patch('msprof_analyze.prof_common.path_manager.PathManager.limited_depth_walk')
    @patch(NAMESPACE + 'MsprofDataPreprocessor')
    def test_allocate_text_prof_data_when_msprof_data_exists_then_return_true(self, mock_msprof, mock_walk):
        """Test text prof data allocation when MSPROF data exists"""
        # Mock directory structure
        mock_walk.return_value = [
            (self.TEST_DIR, ["PROF_001_20250101_test"], [])
        ]

        # Mock MSPROF processor
        mock_msprof_processor = Mock()
        mock_msprof_processor.get_data_map.return_value = {1: self.TEST_DIR}
        mock_msprof_processor.get_data_type.return_value = Constant.DB
        mock_msprof.return_value = mock_msprof_processor
        
        allocator = ProfDataAllocate(self.TEST_DIR)
        result = allocator.allocate_text_prof_data()
        
        self.assertTrue(result)
        self.assertEqual(allocator.prof_type, Constant.MSPROF)
        self.assertEqual(allocator.data_type, Constant.DB)

    def test_allocate_text_prof_data_when_invalid_prof_type_then_return_false(self):
        """Test text prof data allocation when prof type is invalid"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        allocator.prof_type = Constant.INVALID
        
        result = allocator.allocate_text_prof_data()
        
        self.assertFalse(result)
    
    def test_set_prof_data_when_given_valid_data_then_set_correctly(self):
        """Test setting prof data with valid input"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        prof_type = Constant.PYTORCH
        data_type = Constant.DB
        data_map = {1: ["/path/to/data"]}
        
        allocator._set_prof_data(prof_type, data_type, data_map)
        
        self.assertEqual(allocator.prof_type, prof_type)
        self.assertEqual(allocator.data_type, data_type)
        self.assertEqual(allocator.data_map, data_map)

    @patch(NAMESPACE + 'logger')
    def test_set_prof_data_when_msmonitor_data_exists_then_log_warning(self, mock_logger):
        """Test setting prof data when MSMonitor data already exists"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        allocator._msmonitor_data_map = {1: ["/path/to/msmonitor.db"]}
        allocator._set_prof_data(Constant.PYTORCH, Constant.DB, {1: ["/path/to/data"]})
        mock_logger.warning.assert_called_once()
        self.assertEqual(allocator.prof_type, Constant.PYTORCH)
        self.assertEqual(allocator.data_type, Constant.DB)

    def test_set_prof_data_when_msmonitor_prof_type_then_set_msmonitor_data(self):
        """Test setting prof data when prof type is MSMonitor"""
        allocator = ProfDataAllocate(self.TEST_DIR)
        prof_type = Constant.MSMONITOR
        data_type = Constant.DB
        data_map = {1: ["/path/to/msmonitor.db"]}
        
        allocator._set_prof_data(prof_type, data_type, data_map)
        
        self.assertEqual(allocator.prof_type, prof_type)
        self.assertEqual(allocator.data_type, data_type)
        self.assertEqual(allocator.data_map, data_map)


if __name__ == '__main__':
    unittest.main()
