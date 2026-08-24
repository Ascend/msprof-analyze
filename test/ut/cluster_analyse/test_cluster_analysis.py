# Copyright (c) 2025-2025, Huawei Technologies Co., Ltd.
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
import sys
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_analysis import cluster_analysis_main
from msprof_analyze.cluster_analyse.cluster_analysis import Interface


NAMESPACE = "msprof_analyze.cluster_analyse"


class TestClusterAnalyseClusterAnalysis(unittest.TestCase):
    """
    test cluster analysis
    solutions: cluster_analysis.py is the entrance of cluster_analysis,
               its main function is parse the argv and run encountered analysis task.
               However, run whole task in UTest is not reasonable, so the main solutions is checking return of failure.
    """

    def setUp(self):
        # argv backup
        self._orig_argv = sys.argv

        self.test_dir = os.path.join(os.path.dirname(__file__), "test_cluster_analysis")
        os.makedirs(self.test_dir, exist_ok=True)
        self.profiling_path = os.path.join(self.test_dir, "profiling_data")
        self.output_path = os.path.join(self.test_dir, "output")

        os.makedirs(self.profiling_path, exist_ok=True)
        os.makedirs(self.output_path, exist_ok=True)

        self.ascend_pt_dir = os.path.join(self.profiling_path, "test_ascend_pt")
        self.ascend_ms_dir = os.path.join(self.profiling_path, "test_ascend_ms")
        self.prof_dir = os.path.join(self.profiling_path, "PROF_114514")

        os.makedirs(self.ascend_pt_dir, exist_ok=True)
        os.makedirs(self.ascend_ms_dir, exist_ok=True)
        os.makedirs(self.prof_dir, exist_ok=True)

    def tearDown(self):
        # restore argv, avoiding argv pollution
        sys.argv = self._orig_argv

        # remove temp
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_interface_data_map_initialization(self):
        """
        test Interface class initialization
        """
        params = {
            Constant.PROFILING_PATH: self.profiling_path,
            Constant.MODE: "all"
        }

        interface = Interface(params)

        # 验证初始数据映射为空
        self.assertEqual(interface.data_map, {})
        self.assertEqual(interface.communication_group, {})
        self.assertEqual(interface.collective_group_dict, {})
        self.assertEqual(interface.communication_ops, [])
        self.assertEqual(interface.matrix_ops, [])

    def test_cluster_analysis_main_should_run_success_and_handle_correct_parameter(self):
        """
        test main entrance basic
        """
        with mock.patch(NAMESPACE + ".cluster_analysis.Interface") as mock_if:
            sys.argv = [
                "cluster_analysis.py",
                "-d", "./tmp/prof",
                "-o", "./tmp/out",
                "-m", "all",
                "--force",
            ]

            # execute cluster entrance
            cluster_analysis_main()

            # assert Interface be called once
            self.assertEqual(mock_if.call_count, 1)
            kwargs = mock_if.call_args[0][0]  # first arg is parameter dict
            self.assertEqual(kwargs["profiling_path"], "./tmp/prof")
            self.assertEqual(kwargs["mode"], "all")
            self.assertEqual(kwargs["output_path"], "./tmp/out")
            self.assertTrue(kwargs["force"])

            # restore origin argv, avoiding argv pollution
            sys.argv = self._orig_argv

    def test_cluster_analysis_main_all_parameters_success(self):
        """
        test main entrance all parameters
        """
        with patch(NAMESPACE + '.cluster_analysis.Interface') as mock_interface:
            # mock class Interface
            mock_interface_instance = MagicMock()
            mock_interface.return_value = mock_interface_instance

            # set all parameters
            sys.argv = [
                "cluster_analysis.py",
                "-d", self.profiling_path,
                "-o", self.output_path,
                "-m", "communication_time",
                "--force",
                "--parallel_mode", "sequential",
                "--export_type", "notebook",
                "--rank_list", "0,1,2",
                "--step_id", "100",
                Constant.EXTRA_ARGS, "--bp", "/data2"
            ]

            cluster_analysis_main()

            # test Interface
            mock_interface.assert_called_once()
            call_args = mock_interface.call_args[0][0]

            self.assertEqual(call_args["profiling_path"], self.profiling_path)
            self.assertEqual(call_args["output_path"], self.output_path)
            self.assertEqual(call_args["mode"], "communication_time")
            self.assertTrue(call_args["force"])
            self.assertEqual(call_args["parallel_mode"], "sequential")
            self.assertEqual(call_args["export_type"], "notebook")
            self.assertEqual(call_args["rank_list"], "0,1,2")
            self.assertEqual(call_args["step_id"], 100)

    def test_allocate_prof_data_pytorch_only_will_success(self):
        """
        test data pytorch only
        """
        with patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # mock ProfDataAllocate
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "data0", "rank1": "data1"}
            mock_allocator_instance.data_type = "db"
            mock_allocator_instance.prof_type = Constant.PYTORCH
            mock_allocator.return_value = mock_allocator_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "all"
            }

            interface = Interface(params)
            result = interface.allocate_prof_data()

            expected = {
                Constant.DATA_MAP: {"rank0": "data0", "rank1": "data1"},
                Constant.DATA_TYPE: "db",
                Constant.PROFILING_TYPE: Constant.PYTORCH
            }
            self.assertEqual(result, expected)

    def test_allocate_prof_data_mindspore_only_will_success(self):
        """
        test data mindspore only
        """
        with patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # mock ProfDataAllocate
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "data0"}
            mock_allocator_instance.data_type = "db"
            mock_allocator_instance.prof_type = Constant.MINDSPORE
            mock_allocator.return_value = mock_allocator_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "all"
            }

            interface = Interface(params)
            result = interface.allocate_prof_data()

            expected = {
                Constant.DATA_MAP: {"rank0": "data0"},
                Constant.DATA_TYPE: "db",
                Constant.PROFILING_TYPE: Constant.MINDSPORE
            }
            self.assertEqual(result, expected)

    def test_allocate_prof_data_msprof_only_will_success(self):
        """
        test data msprof only
        """
        with patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # mock ProfDataAllocate
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "prof_data"}
            mock_allocator_instance.data_type = "db"
            mock_allocator_instance.prof_type = Constant.MSPROF
            mock_allocator.return_value = mock_allocator_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "all"
            }

            interface = Interface(params)
            result = interface.allocate_prof_data()

            expected = {
                Constant.DATA_MAP: {"rank0": "prof_data"},
                Constant.DATA_TYPE: "db",
                Constant.PROFILING_TYPE: Constant.MSPROF
            }
            self.assertEqual(result, expected)

    def test_allocate_prof_data_both_frameworks_will_return_error(self):
        """
        test data both-frameworks error
        """
        with patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # mock ProfDataAllocate to return False (simulating both frameworks error)
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = False
            mock_allocator.return_value = mock_allocator_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "all"
            }

            interface = Interface(params)
            result = interface.allocate_prof_data()

            # assert return empty dict for data will not be process
            self.assertEqual(result, {})

    def test_run_failure_no_data_map(self):
        """
        test Interface.run method failure when no data map
        """
        with patch(NAMESPACE + '.cluster_analysis.PathManager') as mock_path_manager, \
             patch(NAMESPACE + '.cluster_analysis.logger') as mock_logger, \
             patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # Mock path manager checks
            mock_path_manager.check_input_directory_path.return_value = None
            mock_path_manager.check_path_owner_consistent.return_value = None

            # Mock ProfDataAllocate to return empty data
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {}
            mock_allocator_instance.data_type = "db"
            mock_allocator_instance.prof_type = Constant.PYTORCH
            mock_allocator.return_value = mock_allocator_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "all",
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.output_path
            }

            interface = Interface(params)
            interface.run()

            # Verify warning log for no data
            mock_logger.warning.assert_called_with("Can not get rank info or profiling data.")

    def test_run_failure_text_data_with_recipe_mode(self):
        """
        test Interface.run method failure when text data with recipe mode
        """
        with patch(NAMESPACE + '.cluster_analysis.PathManager') as mock_path_manager, \
             patch(NAMESPACE + '.cluster_analysis.logger') as mock_logger, \
             patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # Mock path manager checks
            mock_path_manager.check_input_directory_path.return_value = None
            mock_path_manager.check_path_owner_consistent.return_value = None

            # Mock ProfDataAllocate returns text data type
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "data0"}
            mock_allocator_instance.data_type = "text"
            mock_allocator_instance.prof_type = Constant.PYTORCH
            mock_allocator.return_value = mock_allocator_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "freq_analysis",  # recipe mode
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.output_path
            }

            interface = Interface(params)
            interface.run()

            # Verify error log for text data with recipe mode
            mock_logger.error.assert_called_with("The current analysis node only supports DB as input data."
                                                 " Please check.")

    def test_run_with_db_comm_mode(self):
        """
        test Interface.run method with db communication mode
        """
        with patch(NAMESPACE + '.cluster_analysis.PathManager') as mock_path_manager, \
             patch(NAMESPACE + '.cluster_analysis.logger'), \
             patch(NAMESPACE + '.cluster_analysis.AnalysisFacade') as mock_analysis_facade, \
             patch(NAMESPACE + '.cluster_analysis.FileManager') as mock_file_manager, \
             patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # Mock path manager checks
            mock_path_manager.check_input_directory_path.return_value = None
            mock_path_manager.check_path_owner_consistent.return_value = None
            mock_path_manager.check_path_writeable.return_value = None

            # Mock ProfDataAllocate
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "data0"}
            mock_allocator_instance.data_type = "db"
            mock_allocator_instance.prof_type = Constant.PYTORCH
            mock_allocator.return_value = mock_allocator_instance

            # Mock file manager
            mock_file_manager.create_output_dir.return_value = None

            # Mock analysis facade
            mock_analysis_facade_instance = MagicMock()
            mock_analysis_facade.return_value = mock_analysis_facade_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "communication_time",
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.output_path
            }

            interface = Interface(params)
            interface.run()

            # Verify analysis facade is called
            mock_analysis_facade.assert_called()
            mock_analysis_facade_instance.cluster_analyze.assert_called()
            mock_file_manager.create_output_dir.assert_called_once_with(self.output_path, is_overwrite=True)

    def test_run_with_all_mode(self):
        """
        test Interface.run method with 'all' mode
        """
        with patch(NAMESPACE + '.cluster_analysis.PathManager') as mock_path_manager, \
             patch(NAMESPACE + '.cluster_analysis.logger'), \
             patch(NAMESPACE + '.cluster_analysis.AnalysisFacade') as mock_analysis_facade, \
             patch(NAMESPACE + '.cluster_analysis.FileManager') as mock_file_manager, \
             patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            # Mock path manager checks
            mock_path_manager.check_input_directory_path.return_value = None
            mock_path_manager.check_path_owner_consistent.return_value = None
            mock_path_manager.check_path_writeable.return_value = None

            # Mock ProfDataAllocate
            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "data0"}
            mock_allocator_instance.data_type = "db"
            mock_allocator_instance.prof_type = Constant.PYTORCH
            mock_allocator.return_value = mock_allocator_instance

            # Mock file manager
            mock_file_manager.create_output_dir.return_value = None

            # Mock analysis facade
            mock_analysis_facade_instance = MagicMock()
            mock_analysis_facade.return_value = mock_analysis_facade_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "all",
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.output_path
            }

            interface = Interface(params)
            interface.run()

            # Verify analysis facade
            mock_analysis_facade.assert_called()
            mock_analysis_facade_instance.cluster_analyze.assert_called()
            mock_file_manager.create_output_dir.assert_called_once_with(self.output_path, is_overwrite=True)

    def test_run_with_text_comm_mode_generates_comm_data(self):
        """
        test Interface.run method generates communication data for text input
        """
        with patch(NAMESPACE + '.cluster_analysis.PathManager') as mock_path_manager, \
             patch(NAMESPACE + '.cluster_analysis.CommunicationJsonGroup') as mock_comm_group_cls, \
             patch(NAMESPACE + '.cluster_analysis.AnalysisFacade') as mock_analysis_facade, \
             patch(NAMESPACE + '.cluster_analysis.FileManager') as mock_file_manager, \
             patch(NAMESPACE + '.cluster_analysis.ProfDataAllocate') as mock_allocator:

            mock_path_manager.check_input_directory_path.return_value = None
            mock_path_manager.check_path_owner_consistent.return_value = None
            mock_path_manager.check_path_writeable.return_value = None

            mock_allocator_instance = MagicMock()
            mock_allocator_instance.allocate_prof_data.return_value = True
            mock_allocator_instance.data_map = {"rank0": "data0"}
            mock_allocator_instance.data_type = Constant.TEXT
            mock_allocator_instance.prof_type = Constant.PYTORCH
            mock_allocator.return_value = mock_allocator_instance

            mock_file_manager.create_output_dir.return_value = None

            mock_comm_group_instance = MagicMock()
            mock_comm_group_instance.generate.return_value = {"comm_data": "test"}
            mock_comm_group_cls.return_value = mock_comm_group_instance

            mock_analysis_facade_instance = MagicMock()
            mock_analysis_facade.return_value = mock_analysis_facade_instance

            params = {
                Constant.PROFILING_PATH: self.profiling_path,
                Constant.MODE: "communication_time",
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.output_path
            }

            interface = Interface(params)
            interface.run()

            mock_comm_group_cls.assert_called_once()
            mock_comm_group_instance.generate.assert_called_once()
            mock_analysis_facade.assert_called_once()
            mock_analysis_facade_instance.cluster_analyze.assert_called_once()
            mock_file_manager.create_output_dir.assert_called_once_with(self.output_path)
