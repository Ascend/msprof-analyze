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
import stat
import json
import multiprocessing
import unittest

from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes


class TestCompatibleGcAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    interface = None

    @staticmethod
    def run_should_run_success_when_trace_view_not_contain_gc_events():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.CONJECTURED_GC_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("ConjecturedGcAnalysis", [])) == 0
        result.clear()

    @staticmethod
    def run_should_run_success_when_trace_view_contain_gc_events():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.CONJECTURED_GC_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("ConjecturedGcAnalysis", {}).get("data", [])) == 2
        result.clear()

    @classmethod
    def create_common_events(cls):
        # Python pid
        py_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 1, "args": {"name": "Python"}}
        # ascend pid
        ascend_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 4, "args": {"name": "Ascend Hardware"}}
        # cann pid
        cann_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 5, "args": {"name": "CANN"}}
        # ascend hardware ops
        ah_event1 = {
            "ph": "X", "name": "Slice1", "ts": "1699529623106750", "dur": 100, "tid": 3, "pid": 4,
            "args": {"Task Type": "AI_CORE"}
        }
        ah_event2 = {
            "ph": "X", "name": "Matmul", "ts": "1699529623106888", "dur": 80, "tid": 3, "pid": 4,
            "args": {"Task Type": "AI_CORE"}
        }
        # free event
        free_event1 = {
            "name": "Free", "pid": 4139906593, "tid": 3, "ts": "1723545784434032.646", "dur": 500000.58, "ph": "X"
        }
        free_event2 = {
            "name": "Free", "pid": 4139906593, "tid": 3, "ts": "1723545784984032.326", "dur": 200000.76, "ph": "X"
        }
        return [py_pid_data, ascend_pid_data, cann_pid_data, ah_event1, ah_event2, free_event1, free_event2]

    @classmethod
    def create_trace_view_with_gc_events(cls):
        # acl apis
        api_event1 = {
            "name": "AscendCL@aclCreateDataBuffer", "pid": 4139906273, "tid": 4042877, "ts": "1723545784534032.000",
            "dur": 20, "args": {"Thread Id": 4042877, "Mode": "ACL_OP", "level": "acl", "id": "aclCreateDataBuffer",
                                "item_id": "0", "connection_id": 63899}, "ph": "X"
        }
        api_event2 = {
            "name": "AscendCL@aclCreateTensorDesc", "pid": 4139906273, "tid": 4042877, "ts": "1723545784556032.450",
            "dur": 40, "args": {"Thread Id": 4042877, "Mode": "ACL_OP", "level": "acl", "id": "aclCreateTensorDesc",
                                "item_id": "0", "connection_id": 63900}, "ph": "X"
        }
        api_event3 = {
            "name": "AscendCL@opCompile", "pid": 4139906273, "tid": 4044446, "ts": "1723545784572032.870",
            "dur": 150.36,
            "args": {"Thread Id": 4044446, "Mode": "ACL_OP", "level": "acl", "id": "opCompile", "item_id": "0",
                     "connection_id": 63992}, "ph": "X"
        }

        raw_data = [*cls.create_common_events(), api_event1, api_event2, api_event3]
        with os.fdopen(os.open(f"{TestCompatibleGcAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    @classmethod
    def create_trace_view_without_gc_events(cls):
        # acl apis
        api_event1 = {
            "name": "AscendCL@aclCreateDataBuffer", "pid": 4139906273, "tid": 4042877, "ts": "1723545784534032.000",
            "dur": 200000, "args": {"Thread Id": 4042877, "Mode": "ACL_OP", "level": "acl", "id": "aclCreateDataBuffer",
                                  "item_id": "0", "connection_id": 63899}, "ph": "X"
        }
        api_event2 = {
            "name": "AscendCL@aclCreateTensorDesc", "pid": 4139906273, "tid": 4042877, "ts": "1723545784556032.450",
            "dur": 400000, "args": {"Thread Id": 4042877, "Mode": "ACL_OP", "level": "acl", "id": "aclCreateTensorDesc",
                                  "item_id": "0", "connection_id": 63900}, "ph": "X"
        }
        api_event3 = {
            "name": "AscendCL@opCompile", "pid": 4139906273, "tid": 4044446, "ts": "1723545784992032.870",
            "dur": 1500000.36, "args": {"Thread Id": 4044446, "Mode": "ACL_OP", "level": "acl", "id": "opCompile",
                                      "item_id": "0", "connection_id": 63992}, "ph": "X"
        }

        raw_data = [*cls.create_common_events(), api_event1, api_event2, api_event3]
        with os.fdopen(os.open(f"{TestCompatibleGcAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    @classmethod
    def clear_htmls(cls):
        current_path = os.path.dirname(os.path.abspath(__file__))
        for filename in os.listdir(current_path):
            # 检查文件是否以“att”开头
            if filename.startswith("mstt"):
                # 构建文件的完整路径
                file_path = os.path.join(current_path, filename)
                # 删除文件
                os.remove(file_path)

    def tearDown(self):
        if os.path.exists(TestCompatibleGcAdvice.TMP_DIR):
            shutil.rmtree(TestCompatibleGcAdvice.TMP_DIR)
        self.clear_htmls()

    def setUp(self):
        if os.path.exists(TestCompatibleGcAdvice.TMP_DIR):
            shutil.rmtree(TestCompatibleGcAdvice.TMP_DIR)
        if not os.path.exists(TestCompatibleGcAdvice.TMP_DIR):
            os.makedirs(TestCompatibleGcAdvice.TMP_DIR)
        if not os.path.exists(TestCompatibleGcAdvice.OUTPUT_DIR):
            os.makedirs(TestCompatibleGcAdvice.OUTPUT_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_trace_view_contain_gc_events(self):
        self.create_trace_view_with_gc_events()
        new_process = multiprocessing.Process(
            target=self.run_should_run_success_when_trace_view_contain_gc_events)
        new_process.start()
        new_process.join()

    def test_run_should_run_success_when_trace_view_not_contain_gc_events(self):
        self.create_trace_view_without_gc_events()
        new_process = multiprocessing.Process(
            target=self.run_should_run_success_when_trace_view_not_contain_gc_events)
        new_process.start()
        new_process.join()
