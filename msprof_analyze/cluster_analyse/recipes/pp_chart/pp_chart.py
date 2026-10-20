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

from collections import defaultdict
import json
import os
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.cluster_analyse.recipes.mstx2commop.mstx2commop import Mstx2Commop
from msprof_analyze.cluster_analyse.recipes.p2p_pairing.p2p_pairing import P2PPairing
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_exports.pp_chart_export import PPChartExport

logger = get_logger()


def filter_non_overlapping(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = []
    last_end = -1
    for _, row in df.iterrows():
        if row['startNs'] >= last_end:
            result.append(row)
            last_end = row['endNs']
    return pd.DataFrame(result)


class PPChart(BaseRecipeAnalysis):
    FORWARD_STAGE_0 = "FORWARD_STAGE_0"
    FORWARD_STAGE_1 = "FORWARD_STAGE_1"  # 表示一个microbatch在同一张卡的两个stage
    BACKWARD_STAGE_0 = "BACKWARD_STAGE_0"
    BACKWARD_STAGE_1 = "BACKWARD_STAGE_1"
    STEP_TASK_INFO = "StepTaskInfo"
    LOGITS = "logits"

    def __init__(self, params):
        super().__init__(params)
        logger.info("PPChart init.")
        self.params = params
        self.micro_batch_id_dict = defaultdict(list)
        self.pp_stage_mstx_num = defaultdict(int)
        self.micro_batch_num = None
        self.pp_type = None
        self.distributed_args = None
        self.load_pp_info()

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @staticmethod
    def generate_dualpipev_schedule(pp_size, num_microbatches):
        num_microbatches = num_microbatches * 2
        num_warmup_stages = [0] * pp_size
        num_interleaved_forward_stages = [0] * pp_size
        num_1b1w1f_stages = [0] * pp_size
        num_overlap_stages = [0] * pp_size
        num_1b1overlap_stages = [0] * pp_size
        num_interleaved_backward_stages = [0] * pp_size
        num_cooldown_stages = [0] * pp_size
        pp_size *= 2
        for i in range(pp_size // 2):
            num_warmup_stages[i] = pp_size - 2 - i * 2
            num_interleaved_forward_stages[i] = i + 1  # 每个单位是一组1f1f
            num_1b1w1f_stages[i] = pp_size // 2 - i - 1
            num_overlap_stages[i] = num_microbatches - pp_size * 2 + i * 2 + 2
            num_1b1overlap_stages[i] = (pp_size // 2 - i - 1) * 2
            num_interleaved_backward_stages[i] = i + 1
            num_cooldown_stages[i] = [i + 1, pp_size - 2 * i - 2, i + 1]
        schedule_all_stages = {
            'warmup': num_warmup_stages,
            'interleaved_forward': num_interleaved_forward_stages,
            '1b1w1f': num_1b1w1f_stages,
            'overlap': num_overlap_stages,
            '1b1overlap': num_1b1overlap_stages,
            'interleaved_backward': num_interleaved_backward_stages,
            'cooldown': num_cooldown_stages,
        }
        return schedule_all_stages

    def calculate_micro_batch_id_for_dualpipev(self):
        pp_size = self.distributed_args.get(self.PP_SIZE)
        if self.micro_batch_num is None or self.micro_batch_num < pp_size * 2:
            logger.error("The micro_batch_num is less than pp_size * 2, please set it to a larger value.")
            return
        schedule_all_stages = self.generate_dualpipev_schedule(pp_size, self.micro_batch_num)
        cur_micro_batch_id_dict = defaultdict(dict)
        flag = defaultdict(bool)  # 标识最后一个阶段是BACKWARD_STAGE_0开头还是BACKWARD_STAGE_1开头
        for stage_name, stage_num in schedule_all_stages.items():  # pylint: disable=too-many-nested-blocks
            for i, num in enumerate(stage_num):
                last_forward_id_0 = cur_micro_batch_id_dict[i].setdefault(self.FORWARD_STAGE_0, -1)
                last_forward_id_1 = cur_micro_batch_id_dict[i].setdefault(self.FORWARD_STAGE_1, -1)
                last_backward_id_0 = cur_micro_batch_id_dict[i].setdefault(self.BACKWARD_STAGE_0, -1)
                last_backward_id_1 = cur_micro_batch_id_dict[i].setdefault(self.BACKWARD_STAGE_1, -1)
                if stage_name == "warmup":
                    self.micro_batch_id_dict[i].extend([[str(x), 0] for x in range(num)])
                    cur_micro_batch_id_dict[i][self.FORWARD_STAGE_0] = num - 1
                    self.pp_stage_mstx_num[i] += num
                elif stage_name == "interleaved_forward":
                    for j in range(num):
                        self.micro_batch_id_dict[i].append([str(last_forward_id_0 + j + 1), 1])
                        self.micro_batch_id_dict[i].append([str(self.micro_batch_num + j), 1])
                        cur_micro_batch_id_dict[i][self.FORWARD_STAGE_0] += 1
                    cur_micro_batch_id_dict[i][self.FORWARD_STAGE_1] = self.micro_batch_num + num - 1
                    self.pp_stage_mstx_num[i] += num * 2
                elif stage_name == "1b1w1f":
                    for j in range(num):
                        if i == 0:
                            self.micro_batch_id_dict[i].append([self.LOGITS, 2])
                            self.pp_stage_mstx_num[i] += 1
                        self.micro_batch_id_dict[i].append([f"{self.micro_batch_num + j}b", 2])
                        self.micro_batch_id_dict[i].append([f"{self.micro_batch_num + j}w", 2])
                        self.micro_batch_id_dict[i].append([str(last_forward_id_1 + j + 1), 2])
                        cur_micro_batch_id_dict[i][self.FORWARD_STAGE_1] += 1
                    cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_1] = self.micro_batch_num + num - 1
                    self.pp_stage_mstx_num[i] += num * 3
                elif stage_name == "overlap":
                    for j in range(num // 2):
                        if i == 0:
                            self.micro_batch_id_dict[i].append([self.LOGITS, 3])
                            self.pp_stage_mstx_num[i] += 1
                        if i == pp_size - 1 and j == 0:
                            self.micro_batch_id_dict[i].append([f"{last_forward_id_0 + j + 1}F", 3])
                            self.micro_batch_id_dict[i].append([f"{last_backward_id_1 + j + 1}B", 3])
                            self.pp_stage_mstx_num[i] += 1
                        else:
                            self.micro_batch_id_dict[i].append(
                                [f"{last_forward_id_0 + j + 1}F+{last_backward_id_1 + j + 1}B", 3]
                            )
                        self.micro_batch_id_dict[i].append(
                            [f"{last_forward_id_1 + j + 1}F+{last_backward_id_0 + j + 1}B", 3]
                        )
                        cur_micro_batch_id_dict[i][self.FORWARD_STAGE_0] += 1
                        cur_micro_batch_id_dict[i][self.FORWARD_STAGE_1] += 1
                        cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_0] += 1
                        cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_1] += 1
                    self.pp_stage_mstx_num[i] += num
                elif stage_name == "1b1overlap":
                    for j in range(num // 2):
                        if i == 0:
                            self.micro_batch_id_dict[i].append([self.LOGITS, 4])
                            self.pp_stage_mstx_num[i] += 1
                        self.micro_batch_id_dict[i].append([f"{last_backward_id_1 + j + 1}B", 4])
                        self.micro_batch_id_dict[i].append(
                            [f"{last_forward_id_1 + j + 1}F+{last_backward_id_0 + j + 1}B", 4]
                        )
                        cur_micro_batch_id_dict[i][self.FORWARD_STAGE_1] += 1
                        cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_0] += 1
                        cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_1] += 1
                    self.pp_stage_mstx_num[i] += num
                elif stage_name == "interleaved_backward":
                    for j in range(num):
                        if j % 2 == 0:
                            if i == 0:
                                self.micro_batch_id_dict[i].append([self.LOGITS, 5])
                                self.pp_stage_mstx_num[i] += 1
                            self.micro_batch_id_dict[i].append([str(f"{last_backward_id_1 + j // 2 + 1}B"), 5])
                            cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_1] += 1
                            flag[i] = True
                        else:
                            self.micro_batch_id_dict[i].append([str(f"{last_backward_id_0 + j // 2 + 1}B"), 5])
                            cur_micro_batch_id_dict[i][self.BACKWARD_STAGE_0] += 1
                            flag[i] = False
                    self.pp_stage_mstx_num[i] += num
                elif stage_name == "cooldown":
                    self.pp_stage_mstx_num[i] += pp_size  # 不开dw分离
                    while (
                        last_backward_id_0 < self.micro_batch_num - 1
                        or last_backward_id_1 < self.micro_batch_num * 2 - 1
                    ):
                        if flag[i]:
                            if last_backward_id_0 < self.micro_batch_num - 1:
                                self.micro_batch_id_dict[i].append([str(f"{last_backward_id_0 + 1}B"), 6])
                                last_backward_id_0 += 1
                            if last_backward_id_1 < self.micro_batch_num * 2 - 1:
                                self.micro_batch_id_dict[i].append([str(f"{last_backward_id_1 + 1}B"), 6])
                                last_backward_id_1 += 1
                        else:
                            if last_backward_id_1 < self.micro_batch_num * 2 - 1:
                                self.micro_batch_id_dict[i].append([str(f"{last_backward_id_1 + 1}B"), 6])
                                last_backward_id_1 += 1
                            if last_backward_id_0 < self.micro_batch_num - 1:
                                self.micro_batch_id_dict[i].append([str(f"{last_backward_id_0 + 1}B"), 6])
                                last_backward_id_0 += 1

    def load_pp_info(self):
        rank_id = list(self._data_map.keys())[0]
        rank_path = self._data_map[rank_id]
        db_path = self._get_profiler_db_path(rank_id, rank_path)
        if not os.path.exists(db_path):
            logger.error("Db_file: %s not exist.", db_path)
            return
        try:
            service = DatabaseService(db_path, {})
            service.add_table_for_query("META_DATA", ["name", "value"])
            df = service.query_data().get("META_DATA", None)
            if df is None:
                logger.warning("There is no META_DATA in %s.", db_path)
                return
            pp_info = df.loc[df["name"] == "pp_info", "value"]
            if pp_info.empty:
                logger.warning("pp_info not in profiling files, please input manually.")
                return
            else:
                pp_info = json.loads(pp_info.values[0])
                self.micro_batch_num = pp_info.get("microbatch_num")
                self.pp_type = pp_info.get("pp_type").lower()
        except Exception as err:
            logger.error(err)
            logger.error("pp_info not in profiling files, please input manually.")

    def mapper_func_for_dualpipev(self, context):
        return context.wait(
            context.map(
                self._mapper_func_for_dualpipev,
                self._get_rank_db(),
                analysis_class=self._recipe_name,
                rank_pp_stage_map=self.map_rank_pp_stage(self.distributed_args),
                pp_stage_mstx_num=self.pp_stage_mstx_num,
                micro_batch_id_dict=self.micro_batch_id_dict,
            )
        )

    def run_mstx2commop_recipe(self, context):
        """
        Run Recipe to create Mstx2Commop table
        """
        logger.info("Run Mstx2Commop recipe.")
        try:
            group_map_recipe = Mstx2Commop(self.params)
            group_map_recipe.run(context, copy_db=False)
        except Exception as e:
            logger.error("Run Mstx2Commop recipe failed: %s!", e)
            return False
        return True

    def run_p2p_pairing_recipe(self, context):
        """
        Run Recipe to create CommunicationGroupMapping table
        """
        logger.info("Run P2PPairing recipe.")
        try:
            group_map_recipe = P2PPairing(self.params)
            group_map_recipe.run(context)
        except Exception as e:
            logger.error("Run P2PPairing recipe failed: %s!", e)
            return False
        return True

    def run(self, context):
        if self._export_type != Constant.DB:
            logger.error("cluster_time_summary only supports export db.")
            return
        if not self.run_mstx2commop_recipe(context) or not self.run_p2p_pairing_recipe(context):
            return

        if self.pp_type == "dualpipev" and self._prof_type != Constant.MSMONITOR:
            self.distributed_args = self.load_distributed_args()
            if self.distributed_args:
                self.calculate_micro_batch_id_for_dualpipev()
                res = self.mapper_func_for_dualpipev(context)  # 忽略返回值
            else:
                logger.warning("The parallel strategy is lost.")
                res = None
        else:
            res = self.mapper_func(context)  # 忽略返回值
        if res:
            logger.info("PPChart finished.")

    def _mapper_func_for_dualpipev(
        self, data_map, analysis_class, rank_pp_stage_map, pp_stage_mstx_num, micro_batch_id_dict
    ):
        """
        rank_pp_stage_map: 记录rank与pp_stage的映射，可以知道某个rank属于哪个pp_stage
        pp_stage_mstx_num： 每个pp_stage预期的前反向的总打点数
        micro_batch_id_dict: 每个pp_stage的microbatch_id信息以及属于dualpipeV的哪个阶段，示例如下
        {
        0: [ ["0", 0], [ "2", 0], ..., ["7F+13B", 3], ...]
        ....
        }
        """
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = PPChartExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning("There is no mstx data in %s.", profiler_db_path)
            return
        rank_id = data_map.get(Constant.RANK_ID)
        pp_stage = rank_pp_stage_map.get(rank_id)
        if pp_stage is None:
            logger.error("The rank %s does not belong to any PP stage.", rank_id)
            return
        df = filter_non_overlapping(df)
        df["name"] = ""
        df["type"] = 0

        def match_mstx_name(group):
            if len(group) != pp_stage_mstx_num[pp_stage]:
                logger.error("The number of mstx_count should be %s, not %s.", pp_stage_mstx_num[pp_stage], len(group))
                return group
            for idx, (i, row) in enumerate(group.iterrows()):
                micro_batch_id_info = micro_batch_id_dict[pp_stage][idx]
                group.at[i, "name"] = micro_batch_id_info[0]
                group.at[i, "type"] = micro_batch_id_info[1]
            return group

        df = df.groupby("step").apply(match_mstx_name)
        result = df[["name", "startNs", "endNs", "type"]]
        self.dump_data(
            data=result,
            file_name="",
            table_name=self.STEP_TASK_INFO,
            index=False,
            custom_db_path=data_map.get(Constant.PROFILER_DB_PATH),
        )

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = PPChartExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning("There is no mstx data in %s.", profiler_db_path)
            return
        df["name"] = df["msg"].apply(lambda x: "FP" if "forward" in x.lower() else "BP")
        df['type'] = df['name'].map({'FP': 0, 'BP': 1})
        result = df[["name", "startNs", "endNs", "type"]]
        self.dump_data(
            data=result,
            file_name="",
            table_name=self.STEP_TASK_INFO,
            index=False,
            custom_db_path=data_map.get(Constant.PROFILER_DB_PATH),
        )
