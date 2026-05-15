# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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

import multiprocessing
import os
import time
from collections import defaultdict
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_advice_base import ClusterAdviceBase
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.common_func_advisor.trace_view_preprocessor import FineTraceViewData
from msprof_analyze.advisor.advisor_backend.common_func_advisor.trace_view_preprocessor import TraceViewPreProcessor
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.cluster_data_preprocess.pytorch_data_preprocessor import PytorchDataPreprocessor
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


@dataclass
class PipelineTimeSlice:
    start: str = ""
    end: str = ""
    slice_type: str = ""
    bp_timeslice: list = None

    def __post_init__(self):
        self.bp_timeslice = self.bp_timeslice or []


class PipelineTraceViewer:
    STAGE_COLOR = "good"
    BUBBLE_COLOR = "generic_work"
    FP_COLOR = "good"
    BP_COLOR = "bad"
    PIPLINE_VIEW = "Pipeline View"
    STAGE = "Stage"
    BUBBLE = "Bubble"
    FP = "FP"
    BP = "BP"

    COLORS = {
        STAGE: STAGE_COLOR,
        BUBBLE: BUBBLE_COLOR,
        FP: FP_COLOR,
        BP: BP_COLOR
    }

    def gen_stage_bubble_trace_data(self, rank_id: int, timeslice_list: List[PipelineTimeSlice]) -> List[Dict]:
        """
        generate stage bubble trace json data
        """
        rank_str = f'Rank {rank_id}'
        trace_data = []

        for timeslice in timeslice_list:
            data = self._gen_trace_pair(timeslice.slice_type, timeslice.start,
                                        timeslice.end, self.PIPLINE_VIEW, rank_str)
            trace_data.append(data)

        return trace_data

    def gen_fp_bp_trace_data(self, rank_id: int, timeslice_list: List[PipelineTimeSlice]) -> List[Dict]:
        """
        generate fp bp trace json data
        """
        rank_str = f'Rank {rank_id}'
        trace_data = []

        for timeslice in timeslice_list:
            if timeslice.slice_type == self.BUBBLE:
                data = self._gen_trace_pair(timeslice.slice_type, timeslice.start,
                                            timeslice.end, self.PIPLINE_VIEW, rank_str)
                trace_data.append(data)
            else:
                last_end = timeslice.start
                for bp_bound in timeslice.bp_timeslice:
                    data = self._gen_trace_pair(self.FP, last_end,
                                                bp_bound[0], self.PIPLINE_VIEW, rank_str)
                    trace_data.append(data)
                    last_end = bp_bound[1]

                    data = self._gen_trace_pair(self.BP, bp_bound[0],
                                                bp_bound[1], self.PIPLINE_VIEW, rank_str)
                    trace_data.append(data)

                last_data = self._gen_trace_pair(self.FP, last_end,
                                                 timeslice.end, self.PIPLINE_VIEW, rank_str)
                trace_data.append(last_data)

        return trace_data

    def _gen_trace_pair(self, name: str, start_ts: str, end_ts: str, pid: str, tid: str) -> Dict:
        data = {
            Constant.OP_NAME: name,
            Constant.CNAME: self.COLORS.get(name, self.BUBBLE),
            Constant.PH: Constant.PH_X,
            Constant.PID: pid,
            Constant.OP_TID: tid,
            Constant.TS: start_ts,
            Constant.DUR: str(Decimal(end_ts) - Decimal(start_ts))
        }

        return data


class ClusterPipelineAdvice(ClusterAdviceBase):
    BUBBLE = "Bubble"
    STAGE = "Stage"
    PIPELINE_VIEW = "Pipeline View"
    SAVE_JSON = "pipeline_view.json"

    def __init__(self, collection_path: str, kwargs: dict):
        super().__init__(collection_path)
        self.rank_ids = list(set(kwargs.get("rank_ids", [])))
        self.worker_num = kwargs.get("worker_num", int(multiprocessing.cpu_count() / 2))
        self.rank_prof_dirs = {}
        self.cur_data = []
        self.cur_bottleneck = {}
        self.cur_advices = ""

    @staticmethod
    def load_trace_view_data(json_path) -> Optional[FineTraceViewData]:
        """
        load trace view data from json file and preprocess
        """
        raw_data = FileManager.read_json_file(json_path)
        return TraceViewPreProcessor().process(raw_data)

    @staticmethod
    def double_queue_pop(fp_que: Deque[dict], bp_que: Deque[dict]) -> Tuple[list, list]:
        """
        double queue (fp and bp que) pop alternating algorithm implementation
        """
        res_fp_ops, res_bp_ops = [], []
        pop_fp = fp_que[0][Constant.TS] < bp_que[0][Constant.TS]
        fp_start_op, fp_end_op = fp_que[0], fp_que[0]
        bp_start_op, bp_end_op = bp_que[0], bp_que[0]

        def update_bound_op(que: Deque[dict], start_op: dict, end_op: dict) -> Tuple[dict, dict]:
            """
            update fp and bp bound op
            """
            op = que.popleft()
            op_s = Decimal(op[Constant.TS])
            op_e = op_s + Decimal(op[Constant.DUR])

            start_op = op if op_s < Decimal(start_op[Constant.TS]) else start_op
            end_op = op if op_e > Decimal(end_op[Constant.TS]) + Decimal(end_op[Constant.DUR]) else end_op

            return start_op, end_op

        while fp_que and bp_que:
            if pop_fp:
                if len(fp_que) > 1 and bp_que and fp_que[1][Constant.TS] > bp_que[0][Constant.TS]:
                    pop_fp = False  # pop bp que
                if len(fp_que) == 1:
                    pop_fp = False  # pop bp que

                fp_start_op, fp_end_op = update_bound_op(fp_que, fp_start_op, fp_end_op)

                # time to pop bp que, need to record fp ops and update bp start op
                if not pop_fp:
                    res_fp_ops.append((fp_start_op, fp_end_op))
                    if fp_que:
                        bp_start_op, bp_end_op = bp_que[0], bp_que[0]
            else:
                if len(bp_que) > 1 and fp_que and bp_que[1][Constant.TS] > fp_que[0][Constant.TS]:
                    pop_fp = True  # pop fp que
                if len(bp_que) == 1:
                    pop_fp = True  # pop fp que

                bp_start_op, bp_end_op = update_bound_op(bp_que, bp_start_op, bp_end_op)

                # time to pop fp que, need to record bp ops and update fp start op
                if pop_fp:
                    res_bp_ops.append((bp_start_op, bp_end_op))
                    if bp_que:
                        fp_start_op, fp_end_op = fp_que[0], fp_que[0]

        if fp_que:
            fp_start_op, fp_end_op = fp_que[0], fp_que[0]
            while fp_que:
                fp_start_op, fp_end_op = update_bound_op(fp_que, fp_start_op, fp_end_op)
            res_fp_ops.append((fp_start_op, fp_end_op))

        if bp_que:
            bp_start_op, bp_end_op = bp_que[0], bp_que[0]
            while bp_que:
                bp_start_op, bp_end_op = update_bound_op(bp_que, bp_start_op, bp_end_op)
            res_bp_ops.append((bp_start_op, bp_end_op))

        return res_fp_ops, res_bp_ops

    @staticmethod
    def update_ops_time(ops_list: List[List[dict]], torch_to_npu_links: List[dict],
                        npu_ops_ts_dur: dict) -> List[List[dict]]:
        """
        update fp and bp bound ops time at device by using torch_to_npu_links
        """
        ops_que = deque(ops_list)
        torch_to_npu_que = deque(torch_to_npu_links)
        res = []
        link_stack = []
        while ops_que and torch_to_npu_que:
            link = torch_to_npu_que.popleft()
            link_s = Decimal(link[Constant.TS])

            # bound op at framework level
            cpu_op_l, cpu_op_r = ops_que[0][0], ops_que[0][1]
            cpu_op_s = Decimal(cpu_op_l[Constant.TS])
            cpu_op_e = Decimal(cpu_op_r[Constant.TS]) + Decimal(cpu_op_r[Constant.DUR])

            if cpu_op_s < link_s < cpu_op_e:
                link_stack.append(link)
            if link_s > cpu_op_e or \
                    (link_stack and not torch_to_npu_que):
                min_link = link_stack[0]
                max_link = link_stack[-1]

                min_link_s = str(min_link[Constant.ID])
                max_link_s = str(max_link[Constant.ID])
                # for compatibility with old data (ts is float type)
                if isinstance(min_link[Constant.ID], float):
                    cpu_op_l["npu_op_ts"] = min_link_s
                    cpu_op_r["npu_op_ts"] = max_link_s
                else:
                    cpu_op_l["npu_op_ts"] = f"{min_link_s[:-3]}.{min_link_s[-3:]}"
                    cpu_op_r["npu_op_ts"] = f"{max_link_s[:-3]}.{max_link_s[-3:]}"
                cpu_op_l["npu_op_dur"] = npu_ops_ts_dur.get(cpu_op_l["npu_op_ts"], 0)
                cpu_op_r["npu_op_dur"] = npu_ops_ts_dur.get(cpu_op_r["npu_op_ts"], 0)

                res.append([cpu_op_l, cpu_op_r])
                ops_que.popleft()
                link_stack.clear()

        return res

    @staticmethod
    def _align_trace_bound(results: List) -> None:
        """
        align all rank trace bound for better visualization
        """
        start_list, end_list = [], []
        for res in results:
            start_list.append(res[0].start)
            end_list.append(res[-1].end)

        # update all rank trace bound
        for res in results:
            res[0].start = min(start_list)
            res[-1].end = max(end_list)

    def run(self) -> dict:
        """
        Unified entrance interface
        """
        self.rank_prof_dirs = self.get_rank_prof_dirs(self.rank_ids)
        if not self.rank_prof_dirs:
            logger.error("No rank profiling data found, please check the rank ids or dir path.")
            return {}

        self.process()
        self.output()
        self.identify_bottleneck()
        return self.output_format_data

    def process(self) -> None:
        """
        process all rank profiling data by using multi-process
        """
        start_time = time.time()
        logger.info("Start to process %s rank profiling data with %s workers.",
                    str(len(self.rank_prof_dirs)), str(self.worker_num))
        with multiprocessing.Pool(self.worker_num) as pool:
            results = pool.map(self.work, self.rank_prof_dirs.items())

        for (rank_id, _), (res, show_fp_bp) in zip(self.rank_prof_dirs.items(), results):
            if show_fp_bp:
                self.cur_data += PipelineTraceViewer().gen_fp_bp_trace_data(rank_id, res)
            else:
                self.cur_data += PipelineTraceViewer().gen_stage_bubble_trace_data(rank_id, res)
        time_cost = time.time() - start_time
        logger.info("Pipline view data process finished, cost %2f s.", time_cost)

    def work(self, kv: Tuple[int, str]) -> Tuple[List[PipelineTimeSlice], bool]:
        """
        single process worker function
        """
        show_fp_bp = False
        rank_id, rank_prof_dir = kv
        logger.info("[Rank %s] Start to process rank profiling data.", rank_id)
        json_path = os.path.join(rank_prof_dir, Constant.ASCEND_PROFILER_OUTPUT, Constant.TRACE_VIEW_JSON)
        fine_data = self.load_trace_view_data(json_path)
        if not fine_data.hcom_ops or not fine_data.hcom_tids:
            logger.error("[Rank %s] No hcom send recv ops found, make sure the trace view data is "
                         "pipeline parallel sense.", str(rank_id))
            return [], show_fp_bp

        timeslice_list = self.get_pipeline_timeslice(fine_data.hcom_ops, fine_data.hcom_tids, fine_data.min_ts,
                                                     fine_data.max_ts)
        if not fine_data.fp_ops or not fine_data.bp_ops:
            logger.info("[Rank %s] No frameWork data in trace view, only show stage and bubble.",
                        str(rank_id))
        elif len(fine_data.hcom_tids) > 1:
            logger.warning("[Rank %s] More than one hcom tid found, only show stage and bubble.",
                           str(rank_id))
        else:
            logger.info("[Rank %s] Found frameWork data in trace view, show fp bp and bubble.",
                        rank_id)
            bp_ops = self.get_fp_bp_bound_ops(fine_data)
            self.update_stage_fp_bp(timeslice_list, bp_ops)
            show_fp_bp = True
        logger.info("[Rank %s] Rank profiling data process finished.", str(rank_id))

        return timeslice_list, show_fp_bp

    def identify_bottleneck(self) -> None:
        pass

    def output(self) -> None:
        """
        output result
        """
        self.cur_data.append(
            {
                Constant.OP_NAME: Constant.PROCESS_NAME,
                Constant.PH: Constant.PH_META,
                Constant.PID: self.PIPELINE_VIEW,
                Constant.OP_TID: self.PIPELINE_VIEW,
                Constant.ARGS: {
                    Constant.OP_NAME: self.PIPELINE_VIEW
                }
            }
        )
        self.output_format_data[self.DATA] = self.cur_data
        self.output_format_data[self.BOTTLENECK] = self.cur_bottleneck
        self.output_format_data[self.ADVICE] = self.cur_advices

    def get_rank_prof_dirs(self, rank_ids: list) -> Dict[int, str]:
        """
        get rank profiling directories by rank ids
        """
        rank_prof_dirs = defaultdict(str)
        prof_dirs = []
        for prof_dir in os.listdir(self.collection_path):
            if prof_dir.endswith(Constant.PT_PROF_SUFFIX):
                prof_dirs.append(os.path.join(self.collection_path, prof_dir))

        data_map = PytorchDataPreprocessor(prof_dirs).get_data_map()
        for rank_id in rank_ids:
            if rank_id in data_map:
                rank_prof_dirs[rank_id] = data_map[rank_id]
            else:
                logger.warning('Rank %s not found in %s', str(rank_id), str(self.collection_path))

        return rank_prof_dirs

    def get_fp_bp_bound_ops(self, fine_data: FineTraceViewData) -> List[List[dict]]:
        """
        get fp and bp bound ops by using double queue alternating pop algorithm and
        update fp and bp bound ops time at device by using torch_to_npu_links
        """
        fp_que = deque(fine_data.fp_ops)
        bp_que = deque(fine_data.bp_ops)

        # get fp and bp bound ops
        _, res_bp_ops = self.double_queue_pop(fp_que, bp_que)

        # according to torch_to_npu_links, split fp and bp timeslice
        bp_ops = self.update_ops_time(res_bp_ops, fine_data.torch_to_npu_links, fine_data.npu_ops_ts_dur)
        return bp_ops

    def get_pipeline_timeslice(self, hcom_ops: list, hcom_tids: list,
                               min_ts: str, max_ts: str) -> List[PipelineTimeSlice]:
        """
        get pipeline timeslice by using hcom ops
        """
        timeslice_list = []
        last_op_end = None
        if len(hcom_tids) > 1:
            logger.warning("More than one hcom tid found, default to show minimal tid pipeline view.")

        for op in hcom_ops:
            if op[Constant.OP_TID] == min(hcom_tids):
                # gap between two hcom ops
                if last_op_end:
                    timeslice_list.append(PipelineTimeSlice(str(last_op_end), op[Constant.TS], self.STAGE))
                # hcom op
                last_op_end = Decimal(op[Constant.TS]) + Decimal(op[Constant.DUR])
                timeslice_list.append(PipelineTimeSlice(op[Constant.TS], str(last_op_end), self.BUBBLE))

        # add start STAGE and end STAGE
        timeslice_list.insert(0, PipelineTimeSlice(min_ts, timeslice_list[0].start, self.STAGE))
        timeslice_list.insert(len(timeslice_list), PipelineTimeSlice(timeslice_list[-1].end, max_ts, self.STAGE))
        return timeslice_list

    def update_stage_fp_bp(self, timeslice_list: List[PipelineTimeSlice],
                           bp_ops: List[List[dict]]) -> None:
        """
        update stage fp and bp time
        """
        pipeline_que = deque(timeslice_list)
        bp_bound_que = deque(bp_ops)

        while pipeline_que and bp_bound_que:
            while pipeline_que[0].slice_type != self.STAGE:
                pipeline_que.popleft()
                if not pipeline_que:
                    return None

            bp_bound_data = bp_bound_que[0]
            bp_bound_s = Decimal(bp_bound_data[0]['npu_op_ts'])
            bp_bound_e = Decimal(bp_bound_data[1]['npu_op_ts']) + Decimal(bp_bound_data[1]['npu_op_dur'])

            pipeline_s = Decimal(pipeline_que[0].start)
            pipeline_e = Decimal(pipeline_que[0].end)

            if pipeline_s <= bp_bound_s and bp_bound_e <= pipeline_e:
                pipeline_que[0].bp_timeslice.append((str(bp_bound_s), str(bp_bound_e)))
                bp_bound_que.popleft()
            elif bp_bound_s > pipeline_e:
                pipeline_que.popleft()
            else:
                bp_bound_que.popleft()
