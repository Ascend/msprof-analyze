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
from unittest import mock
from collections import deque
from collections import defaultdict

from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_pipeline_advice import ClusterPipelineAdvice
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_pipeline_advice import FineTraceViewData
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_pipeline_advice import PipelineTimeSlice
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_pipeline_advice import PipelineTraceViewer


class TestClusterPipelineAdvice(unittest.TestCase):

    def test_load_trace_view_data_should_return_none_when_input_json_empty(self):
        with mock.patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file', return_value=None):
            advice = ClusterPipelineAdvice('./tmp_dir', {})
            self.assertEqual(advice.load_trace_view_data('test'), None)

    def test_load_trace_view_data_should_return_correct_when_input_json_not_empty(self):
        # Python pid
        py_pid_data = {"ph": "M", "name": "process_name", "tid": 1, "pid": 1, "args": {"name": "Python"}}
        # ascend pid
        ascend_pid_data = {"ph": "M", "name": "process_name", "tid": 4, "pid": 4, "args": {"name": "Ascend Hardware"}}
        # FP ops
        fp_op1 = {"ph": "X", "name": "aten::empty", "ts": "201", "dur": 2, "tid": 2, "pid": 1, "args": {}}
        fp_op2 = {"ph": "X", "name": "c10d::empty", "ts": "203", "dur": 4, "tid": 2, "pid": 1, "args": {}}
        # BP ops
        bp_op1 = {"ph": "X", "name": "aten::item", "ts": "210", "dur": 6, "tid": 3, "pid": 1, "args": {}}
        bp_op2 = {"ph": "X", "name": "autograd::add", "ts": "220", "dur": 8, "tid": 3, "pid": 1, "args": {}}
        # hcom ops
        hcom_op1 = {"ph": "X", "name": "hcom_BatchSendRecv__101_0_1", "ts": "240", "dur": 10, "tid": 5, "pid": 3,
                    "args": {}}
        hcom_op2 = {"ph": "X", "name": "hcom_send__101_0_1", "ts": "260", "dur": 12, "tid": 6, "pid": 3, "args": {}}
        hcom_op3 = {"ph": "X", "name": "hcom_receive__101_0_1", "ts": "280", "dur": 14, "tid": 5, "pid": 3, "args": {}}
        # torch to npu links
        torch_to_npu_link = {"ph": "s", "bp": "e", "name": "torch_to_npu", "ts": "2", "pid": 2, "tid": 2,
                             "cat": "async_npu"}
        # npu ops
        npu_op1 = {"ph": "X", "name": "ZerosLike1", "ts": "15", "dur": 16, "tid": 2, "pid": 4, "args": {}}
        npu_op2 = {"ph": "X", "name": "ZerosLike2", "ts": "17", "dur": 18, "tid": 2, "pid": 4, "args": {}}
        raw_data = [
            py_pid_data,
            ascend_pid_data,
            fp_op1, fp_op2,
            bp_op1, bp_op2,
            hcom_op1, hcom_op2, hcom_op3,
            torch_to_npu_link,
            npu_op1, npu_op2
        ]

        except_res = FineTraceViewData(
            py_pid=1,
            fp_tid=2,
            bp_tid=3,
            ascend_pid=4,
            min_ts="240",
            max_ts="280",
            hcom_tids=[5, 6],
            fp_ops=[fp_op1, fp_op2],
            bp_ops=[bp_op1, bp_op2],
            hcom_ops=[hcom_op1, hcom_op2, hcom_op3],
            npu_ops_ts_dur={"15": 16, "17": 18},
            torch_to_npu_links=[torch_to_npu_link],
        )
        with mock.patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file', return_value=raw_data):
            advice = ClusterPipelineAdvice('./tmp_dir', {})
            check_res = advice.load_trace_view_data('test')
            self.assertEqual(check_res, except_res)

    def test_get_rank_prof_dirs_should_return_empty_when_rankids_empty(self):
        advice = ClusterPipelineAdvice('./', {})
        res = advice.get_rank_prof_dirs(rank_ids=[])
        self.assertEqual(res, defaultdict(str))

    def test_double_queue_pop_should_return_correct_when_queue_not_empty(self):
        fp_op1 = {"ph": "X", "name": "aten::empty", "ts": 1, "dur": 2, "tid": 2, "pid": 1, "args": {}}
        fp_op2 = {"ph": "X", "name": "c10d::empty", "ts": 3, "dur": 4, "tid": 2, "pid": 1, "args": {}}
        bp_op1 = {"ph": "X", "name": "autogard::item", "ts": 5, "dur": 6, "tid": 3, "pid": 1, "args": {}}
        bp_op2 = {"ph": "X", "name": "autogard::add", "ts": 7, "dur": 8, "tid": 3, "pid": 1, "args": {}}
        fp_op3 = {"ph": "X", "name": "aten::empty", "ts": 9, "dur": 10, "tid": 2, "pid": 1, "args": {}}
        fp_op4 = {"ph": "X", "name": "c10d::empty", "ts": 11, "dur": 12, "tid": 2, "pid": 1, "args": {}}
        bp_op3 = {"ph": "X", "name": "autogard::item", "ts": 13, "dur": 14, "tid": 3, "pid": 1, "args": {}}
        bp_op4 = {"ph": "X", "name": "autogard::add", "ts": 15, "dur": 16, "tid": 3, "pid": 1, "args": {}}

        fp_que = deque([fp_op1, fp_op2, fp_op3, fp_op4])
        bp_que = deque([bp_op1, bp_op2, bp_op3, bp_op4])
        advice = ClusterPipelineAdvice('./tmp_dir', {})
        res_fp_ops, res_bp_ops = advice.double_queue_pop(fp_que, bp_que)

        self.assertEqual(res_fp_ops, [(fp_op1, fp_op2), (fp_op3, fp_op4)])
        self.assertEqual(res_bp_ops, [(bp_op1, bp_op2), (bp_op3, bp_op4)])

    def test_get_fp_bp_bound_ops_return_correct_when_bp_ops_not_empty(self):
        torch_to_npu_links = [
            {"ph": "s", "bp": "e", "name": "torch_to_npu", "id": 1000000100, "ts": "1000000000", "pid": 2, "tid": 2,
             "cat": "async_npu"},
            {"ph": "s", "bp": "e", "name": "torch_to_npu", "id": 2000000200, "ts": "2000000000", "pid": 2, "tid": 2,
             "cat": "async_npu"},
        ]
        npu_ops_ts_dur = {"1000000.100": 10, "2000000.200": 20}
        fine_data = FineTraceViewData(torch_to_npu_links=torch_to_npu_links, npu_ops_ts_dur=npu_ops_ts_dur)

        bp_op1 = {"ph": "X", "name": "autogard::item", "ts": str(1000000000 - 100), "dur": 2000, "tid": 3, "pid": 1,
                  "args": {}}
        bp_op2 = {"ph": "X", "name": "autogard::add", "ts": str(2000000000 - 100), "dur": 2000, "tid": 3, "pid": 1,
                  "args": {}}
        res_bp_ops = [(bp_op1, bp_op2)]
        with mock.patch('msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_pipeline_advice.'
                        'ClusterPipelineAdvice.double_queue_pop',
                        return_value=(None, res_bp_ops)):
            advice = ClusterPipelineAdvice('./tmp_dir', {})
            res_check = advice.get_fp_bp_bound_ops(fine_data)
            self.assertEqual(res_check[0][0]['npu_op_ts'], "1000000.100")
            self.assertEqual(res_check[0][0]['npu_op_dur'], 10)
            self.assertEqual(res_check[0][1]['npu_op_ts'], "2000000.200")
            self.assertEqual(res_check[0][1]['npu_op_dur'], 20)

    def test_get_pipeline_timeslice_should_return_correct_when_hcom_ops_and_hcom_tids_not_empty(self):
        hcom_ops = [
            {"ts": "100", "dur": 100, "tid": 5},
            {"ts": "250", "dur": 50, "tid": 6},
            {"ts": "300", "dur": 100, "tid": 5},
            {"ts": "500", "dur": 100, "tid": 5},
        ]
        hcom_tids = [5, 6]
        except_res = [
            PipelineTimeSlice("0", "100", "Stage"),
            PipelineTimeSlice("100", "200", "Bubble"),
            PipelineTimeSlice("200", "300", "Stage"),
            PipelineTimeSlice("300", "400", "Bubble"),
            PipelineTimeSlice("400", "500", "Stage"),
            PipelineTimeSlice("500", "600", "Bubble"),
            PipelineTimeSlice("600", "700", "Stage")
        ]
        advice = ClusterPipelineAdvice('./tmp_dir', {})
        res_check = advice.get_pipeline_timeslice(hcom_ops, hcom_tids, "0", "700")
        self.assertEqual(res_check, except_res)

    def test_update_stage_fp_bp_should_split_correct_fp_bp_when_input_not_empty(self):
        """
            200             300              400             500
            |-----Stage-----|-----Bubble-----|-----Stage-----|

        bp ops: [100,150], [160,200], [200, 250], [260, 265], [270, 300], [350, 380], [390, 410], [430, 460], [510, 520]
        """
        timeslice_list = [
            PipelineTimeSlice("200", "300", "Stage"),
            PipelineTimeSlice("300", "400", "Bubble"),
            PipelineTimeSlice("400", "500", "Stage"),
        ]

        bp_ops = [
            [{'npu_op_ts': '100', 'npu_op_dur': 10}, {'npu_op_ts': '140', 'npu_op_dur': 10}],
            [{'npu_op_ts': '160', 'npu_op_dur': 10}, {'npu_op_ts': '190', 'npu_op_dur': 10}],
            [{'npu_op_ts': '200', 'npu_op_dur': 10}, {'npu_op_ts': '240', 'npu_op_dur': 10}],
            [{'npu_op_ts': '260', 'npu_op_dur': 10}, {'npu_op_ts': '255', 'npu_op_dur': 10}],
            [{'npu_op_ts': '270', 'npu_op_dur': 10}, {'npu_op_ts': '290', 'npu_op_dur': 10}],
            [{'npu_op_ts': '350', 'npu_op_dur': 10}, {'npu_op_ts': '370', 'npu_op_dur': 10}],
            [{'npu_op_ts': '390', 'npu_op_dur': 10}, {'npu_op_ts': '400', 'npu_op_dur': 10}],
            [{'npu_op_ts': '430', 'npu_op_dur': 10}, {'npu_op_ts': '450', 'npu_op_dur': 10}],
            [{'npu_op_ts': '510', 'npu_op_dur': 10}, {'npu_op_ts': '510', 'npu_op_dur': 10}],
        ]

        except_res = [
            PipelineTimeSlice("200", "300", "Stage", bp_timeslice=[('200', '250'), ('260', '265'), ('270', '300')]),
            PipelineTimeSlice("300", "400", "Bubble"),
            PipelineTimeSlice("400", "500", "Stage", bp_timeslice=[('430', '460')])
        ]

        advice = ClusterPipelineAdvice('./tmp_dir', {})
        advice.update_stage_fp_bp(timeslice_list, bp_ops)

        for res, e_res in zip(timeslice_list, except_res):
            self.assertEqual(res, e_res)


class TestPipelineTraceViewer(unittest.TestCase):

    def test_gen_fp_bp_trace_data_should_gen_correct_json_when_input_not_at_bound(self):
        rank_id = 0
        timeslice_list = [
            PipelineTimeSlice("200", "300", "Stage", bp_timeslice=[('210', '250'), ('270', '290')]),
            PipelineTimeSlice("300", "400", "Bubble"),
            PipelineTimeSlice("400", "500", "Stage")
        ]
        except_res = [
            {"name": "FP", "cname": "good", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "200",
             "dur": "10"},
            {"name": "BP", "cname": "bad", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "210",
             "dur": "40"},
            {"name": "FP", "cname": "good", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "250",
             "dur": "20"},
            {"name": "BP", "cname": "bad", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "270",
             "dur": "20"},
            {"name": "FP", "cname": "good", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "290",
             "dur": "10"},
            {"name": "Bubble", "cname": "generic_work", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "300",
             "dur": "100"},
            {"name": "FP", "cname": "good", "ph": "X", "pid": "Pipeline View", "tid": "Rank 0", "ts": "400",
             "dur": "100"},
        ]

        viewer = PipelineTraceViewer()
        res_check = viewer.gen_fp_bp_trace_data(rank_id, timeslice_list)
        self.assertEqual(res_check, except_res)
