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
import unittest

from mock import patch

from msprof_analyze.compare_tools.compare_backend.utils.args_manager import ArgsManager
from msprof_analyze.compare_tools.compare_backend.utils.compare_args import Args
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager


class TestArgsManager(unittest.TestCase):
    def setUp(self):
        ArgsManager._instance = {}

        # 创建模拟参数
        self.args = Args(
            base_profiling_path="/path/to/base/profiling",
            comparison_profiling_path="/path/to/comparison/profiling",
            base_step="1",
            comparison_step="2",
        )

        # 初始化 ArgsManager
        self.args_manager = ArgsManager(self.args)

    def tearDown(self) -> None:
        # 清除单例实例，确保每个测试都是独立的
        ArgsManager._instance = {}

    def test_singleton_pattern(self):
        """测试 ArgsManager 是否遵循单例模式"""
        # 再次创建 ArgsManager 实例
        another_args_manager = ArgsManager(self.args)

        # 验证两个实例是否相同
        self.assertIs(self.args_manager, another_args_manager)

    @patch.object(PathManager, 'check_input_directory_path')
    @patch.object(PathManager, 'check_input_file_path')
    @patch('os.path.exists', return_value=True)
    def test_check_profiling_path_success(self, mock_exists, mock_file_check, mock_directory_check):
        """测试成功检查性能分析路径"""
        # 调用方法应该不会抛出异常
        self.args_manager.check_profiling_path({"profiling_path": "/valid/path"})

        # 验证调用了PathManager.check_input_directory_path
        self.assertEqual(mock_directory_check.call_count, 5)

    @patch.object(PathManager, 'check_input_directory_path')
    @patch.object(PathManager, 'check_input_file_path')
    @patch('os.path.isfile')
    @patch('os.listdir')
    def test_init_with_default_value(self, mock_listdir, mock_isfile, mock_check_file, mock_check_dir):
        """测试初始化 ArgsManager"""
        # 设置模拟返回值
        mock_listdir.return_value = [""]
        mock_isfile.side_effect = [False, True, False, True]

        # 调用初始化方法
        self.args_manager.init()

        self.assertEqual(self.args_manager.base_profiling_path, "/path/to/base/profiling")
        self.assertEqual(self.args_manager.base_step, 1)
        self.assertEqual(self.args_manager.comparison_step, 2)
        self.assertEqual(self.args_manager.comparison_profiling_type, "NPU")
        self.assertEqual(len(self.args_manager.base_path_dict), 4)
        self.assertEqual(len(self.args_manager.comparison_path_dict), 4)

        self.assertTrue(self.args_manager.enable_memory_compare)
        self.assertTrue(self.args_manager.enable_communication_compare)
        self.assertFalse(self.args_manager.use_kernel_type)

    def test_init_with_invalid_max_kernel_num(self):
        """测试输入max_kernel_num非法大于3时的异常分支"""
        ArgsManager._instance = {}
        arg_manager = ArgsManager(Args(
            max_kernel_num=3
        ))
        with self.assertRaises(RuntimeError) as exec_info:
            arg_manager.init()
        self.assertEqual(exec_info.exception.args, ("Invalid param, --max_kernel_num has to be greater than 3",))

    def test_set_compare_type(self):
        """测试设置比较类型"""
        # 测试设置为 OVERALL_COMPARE
        self.args_manager.set_compare_type(Constant.OVERALL_COMPARE)
        self.assertTrue(self.args_manager.enable_profiling_compare)

        # 测试设置为 OPERATOR_COMPARE
        self.args_manager.set_compare_type(Constant.OPERATOR_COMPARE)
        self.assertTrue(self.args_manager.enable_operator_compare)

        # 测试设置为 API_COMPARE
        self.args_manager.set_compare_type(Constant.API_COMPARE)
        self.assertTrue(self.args_manager.enable_api_compare)

        # 测试设置为 KERNEL_COMPARE
        self.args_manager.set_compare_type(Constant.KERNEL_COMPARE)
        self.assertTrue(self.args_manager.enable_kernel_compare)

    @patch.object(PathManager, 'check_input_file_path')
    @patch.object(os.path, 'isfile')
    @patch.object(os.path, 'split')
    @patch.object(os.path, 'splitext')
    @patch.object(FileManager, 'check_json_type')
    def test_parse_profiling_path_json_file(self, mock_check_json_type, mock_splitext,
                                            mock_split, mock_isfile, mock_path_check):
        """测试解析单个JSON文件路径"""
        # 设置模拟返回值
        mock_path_check.return_value = None
        mock_isfile.return_value = True
        mock_split.return_value = ("/path/to", "file.json")
        mock_splitext.return_value = ("file", ".json")
        mock_check_json_type.return_value = Constant.GPU

        # 调用函数
        result = ArgsManager(Args()).parse_profiling_path("/path/to/file.json")

        # 验证结果
        expected_result = {
            Constant.PROFILING_TYPE: Constant.GPU,
            Constant.PROFILING_PATH: "/path/to/file.json",
            Constant.TRACE_PATH: "/path/to/file.json"
        }
        self.assertEqual(result, expected_result)

        # 验证调用了正确的方法
        mock_path_check.assert_called_once_with("/path/to/file.json")
        mock_isfile.assert_called_once_with("/path/to/file.json")
        mock_split.assert_called_once_with("/path/to/file.json")
        mock_splitext.assert_called_once_with("file.json")
        mock_check_json_type.assert_called_once_with("/path/to/file.json")

    @patch.object(PathManager, 'check_input_file_path')
    @patch.object(os.path, 'isfile')
    @patch.object(os.path, 'split')
    @patch.object(os.path, 'splitext')
    def test_parse_profiling_path_db_file(self, mock_splitext, mock_split, mock_isfile, mock_path_check):
        """测试解析单个DB文件路径"""
        # 设置模拟返回值
        mock_path_check.return_value = None
        mock_isfile.return_value = True
        mock_split.return_value = ("/path/to", "ascend_pytorch_profiler.db")
        mock_splitext.return_value = ("ascend_pytorch_profiler", ".db")

        # 调用函数
        result = ArgsManager().parse_profiling_path("/path/to/ascend_pytorch_profiler.db")

        # 验证结果
        expected_result = {
            Constant.PROFILING_TYPE: Constant.NPU,
            Constant.PROFILING_PATH: "/path/to/ascend_pytorch_profiler.db",
            Constant.PROFILER_DB_PATH: "/path/to/ascend_pytorch_profiler.db"
        }
        self.assertEqual(result, expected_result)

    @patch.object(PathManager, 'check_input_file_path')
    @patch.object(os.path, 'isfile')
    @patch.object(os.path, 'split')
    @patch.object(os.path, 'splitext')
    def test_parse_profiling_path_invalid_file_extension(self, mock_splitext, mock_split, mock_isfile, mock_path_check):
        """测试解析无效扩展名的文件路径"""
        # 设置模拟返回值
        mock_path_check.return_value = None
        mock_isfile.return_value = True
        mock_split.return_value = ("/path/to", "file.txt")
        mock_splitext.return_value = ("file", ".txt")

        # 调用函数应该抛出 RuntimeError
        with self.assertRaises(RuntimeError) as context:
            ArgsManager(Args()).parse_profiling_path("/path/to/file.txt")

        # 验证异常消息
        self.assertIn("Invalid profiling path suffix", str(context.exception))

    @patch.object(PathManager, 'check_input_directory_path')
    @patch.object(os.path, 'isfile')
    @patch.object(os.path, 'isdir')
    @patch('os.listdir')
    @patch.object(os.path, 'join')
    def test_parse_profiling_path_directory_with_profiler_info(self, mock_join, mock_listdir,
                                                               mock_isdir, mock_isfile, mock_path_check):
        """测试解析包含 profiler_info.json 的目录路径"""
        # 设置模拟返回值
        mock_path_check.return_value = None
        mock_isfile.side_effect = [False, False]
        mock_isdir.side_effect = [True, False]  # 第一次调用针对目录，第二次调用针对 ASCEND_PROFILER_OUTPUT
        mock_listdir.side_effect = [
            ["profiler_info.json", "other_file.txt"],  # 第一次调用返回目录内容
            []  # 第二次调用返回空列表（模拟没有找到 trace_view.json）
        ]
        mock_join.return_value = "/path/to/directory/profiler_info.json"

        # 调用函数应该抛出 RuntimeError
        with self.assertRaises(RuntimeError) as context:
            ArgsManager(Args()).parse_profiling_path("/path/to/directory")

        # 验证异常消息
        self.assertIn("Invalid profiling path", str(context.exception))

    @patch.object(PathManager, 'check_input_directory_path')
    @patch.object(os.path, 'isfile')
    @patch.object(os.path, 'isdir')
    @patch('os.listdir')
    @patch.object(os.path, 'join')
    def test_parse_profiling_path_directory_with_db_file(self, mock_join, mock_listdir,
                                                         mock_isdir, mock_isfile, mock_path_check):
        """测试解析包含 .db 文件的目录路径"""
        # 设置模拟返回值
        mock_path_check.return_value = None
        mock_isfile.return_value = False
        mock_isdir.side_effect = [True, False]  # 第一次调用针对目录，第二次调用针对 ASCEND_PROFILER_OUTPUT
        mock_listdir.side_effect = [
            ["other_file.txt"],  # 第一次调用返回目录内容（没有 profiler_info.json）
            ["ascend_pytorch_profiler.db", "other_file.txt"]  # 第二次调用返回子目录内容
        ]
        mock_join.side_effect = [
            "/path/to/directory/ASCEND_PROFILER_OUTPUT",  # 第一次调用 join
            "/path/to/directory/ascend_pytorch_profiler.db"  # 第二次调用 join
        ]

        # 调用函数
        result = ArgsManager(Args()).parse_profiling_path("/path/to/directory")

        # 验证结果
        expected_result = {
            Constant.PROFILING_TYPE: Constant.NPU,
            Constant.PROFILING_PATH: "/path/to/directory",
            Constant.PROFILER_DB_PATH: "/path/to/directory/ascend_pytorch_profiler.db",
            Constant.ASCEND_OUTPUT_PATH: "/path/to/directory/ASCEND_PROFILER_OUTPUT"
        }
        self.assertEqual(result, expected_result)

    @patch.object(PathManager, 'check_input_directory_path')
    @patch.object(os.path, 'isfile')
    @patch.object(os.path, 'isdir')
    @patch('os.listdir')
    @patch.object(os.path, 'join')
    def test_parse_profiling_path_directory_with_trace_view_json(self, mock_join, mock_listdir,
                                                                 mock_isdir, mock_isfile, mock_path_check):
        """测试解析包含 trace_view.json 的目录路径"""
        # 设置模拟返回值
        mock_path_check.return_value = None
        mock_isfile.side_effect = [False, True]  # 第一次调用针对目录，第二次调用针对 trace_view.json
        mock_isdir.side_effect = [True, False]  # 第一次调用针对目录，第二次调用针对 ASCEND_PROFILER_OUTPUT
        mock_listdir.side_effect = [
            ["other_file.txt"],  # 第一次调用返回目录内容（没有 profiler_info.json）
            ["trace_view.json", "other_file.txt"]  # 第二次调用返回子目录内容（没有 .db 文件）
        ]
        mock_join.side_effect = [
            "/path/to/directory/ASCEND_PROFILER_OUTPUT",  # 第一次调用 join
            "/path/to/directory/trace_view.json"  # 第二次调用 join
        ]

        # 调用函数
        result = ArgsManager(Args()).parse_profiling_path("/path/to/directory")

        # 验证结果
        expected_result = {
            Constant.PROFILING_TYPE: Constant.NPU,
            Constant.PROFILING_PATH: "/path/to/directory",
            Constant.TRACE_PATH: "/path/to/directory/trace_view.json",
            Constant.ASCEND_OUTPUT_PATH: "/path/to/directory/ASCEND_PROFILER_OUTPUT"
        }
        self.assertEqual(result, expected_result)

    @patch.object(PathManager, 'input_path_common_check')
    def test_parse_profiling_path_path_validation_fails(self, mock_path_check):
        """测试路径验证失败的情况"""
        # 设置模拟抛出异常
        mock_path_check.side_effect = RuntimeError("Invalid path")

        # 调用函数应该抛出相同的异常
        with self.assertRaises(RuntimeError) as context:
            ArgsManager(Args()).parse_profiling_path("/invalid/path")

        # 验证异常消息
        self.assertEqual("Invalid path", str(context.exception))


if __name__ == '__main__':
    unittest.main()
