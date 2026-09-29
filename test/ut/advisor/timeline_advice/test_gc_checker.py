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


class TestGcAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    interface = None

    @staticmethod
    def run_should_run_success_when_trace_view_not_contain_gc_events():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.GC_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("GC分析", [])) == 0
        result.clear()

    @staticmethod
    def run_should_run_success_when_trace_view_contain_gc_events():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.GC_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("GC分析", {}).get("data", [])) == 2
        result.clear()

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

    @classmethod
    def create_common_events(cls):
        # Python pid
        py_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 1, "args": {"name": "Python"}}
        # ascend pid
        ascend_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 4, "args": {"name": "Ascend Hardware"}}
        # ascend pid
        cann_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 5, "args": {"name": "CANN"}}
        # ascend hardware ops
        ah_event1 = {
            "ph": "X", "name": "Slice1", "ts": "1699529623106750", "dur": 100, "tid": 3, "pid": 4,
            "args": {"Task Type": "AI_CORE"}
        }
        ah_event2 = {
            "ph": "X", "name": "Slice2", "ts": "1699529623106888", "dur": 80, "tid": 3, "pid": 4,
            "args": {"Task Type": "AI_CORE"}
        }
        # flow event
        flow_event_s = {"ph": "s", "name": "link1", "id": 1, "tid": 3, "pid": 1, "ts": "200", "args": {}}
        flow_event_e = {"ph": "f", "name": "link1", "id": 1, "tid": 3, "pid": 1, "ts": "1699529623106750", "args": {}}
        return [py_pid_data, ascend_pid_data, cann_pid_data, ah_event1, ah_event2, flow_event_s, flow_event_e]


    @classmethod
    def create_trace_view_with_gc_events(cls):

        # Python GC pid
        py_gc_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 2, "args": {"name": "Python GC"}}

        gc_event1 = {
            "ph": "X", "name": "GC", "ts": "1699529622103750", "dur": 1500, "tid": 3, "pid": 4, "cat": "GC",
            "args": {}
        }
        gc_event2 = {
            "ph": "X", "name": "GC", "ts": "1699529623104750", "dur": 50, "tid": 3, "pid": 4, "cat": "GC",
            "args": {}
        }
        gc_event3 = {
            "ph": "X", "name": "GC", "ts": "1699529623105750", "dur": 50000, "tid": 3, "pid": 4, "cat": "GC",
            "args": {}
        }


        raw_data = [*cls.create_common_events(), py_gc_data, gc_event1, gc_event2, gc_event3]
        with os.fdopen(os.open(f"{TestGcAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    @classmethod
    def create_trace_view_without_gc_events(cls):
        raw_data = cls.create_common_events()
        with os.fdopen(os.open(f"{TestGcAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    def tearDown(self):
        if os.path.exists(TestGcAdvice.TMP_DIR):
            shutil.rmtree(TestGcAdvice.TMP_DIR)
        self.clear_htmls()

    def setUp(self):
        if os.path.exists(TestGcAdvice.TMP_DIR):
            shutil.rmtree(TestGcAdvice.TMP_DIR)
        if not os.path.exists(TestGcAdvice.TMP_DIR):
            os.makedirs(TestGcAdvice.TMP_DIR)
        if not os.path.exists(TestGcAdvice.OUTPUT_DIR):
            os.makedirs(TestGcAdvice.OUTPUT_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_trace_view_contain_gc_events(self):
        self.create_trace_view_with_gc_events()
        self.run_should_run_success_when_trace_view_contain_gc_events()

    def test_run_should_run_success_when_trace_view_not_contain_gc_events(self):
        self.create_trace_view_without_gc_events()
        new_process = multiprocessing.Process(target=self.run_should_run_success_when_trace_view_not_contain_gc_events)
        new_process.start()
        new_process.join()
