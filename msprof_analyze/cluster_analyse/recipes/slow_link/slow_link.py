# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from collections import defaultdict

import pandas as pd
import numpy as np
from tqdm import tqdm

from msprof_analyze.cluster_analyse.common_func.utils import describe_duration
from msprof_analyze.cluster_analyse.common_func.utils import detect_outliers_z_score
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.slow_link_export import SlowLinkExport

logger = get_logger()


class SlowLink(BaseRecipeAnalysis):
    TABLE_SLOW_LINK_SUM = "SlowLinkSum"
    TABLE_SLOW_LINK_OPS = "SlowLinkOps"

    TOP_NUM = "top_num"
    DEFAULT_TOP_NUM = 15

    def __init__(self, params):
        super().__init__(params)
        logger.info("SlowLink init.")
        self.slow_link_sum = []
        self.slow_link_ops = []
        top_num = self._extra_args.get(self.TOP_NUM, self.DEFAULT_TOP_NUM)
        self.top_num = int(top_num) if isinstance(top_num, str) and top_num.isdigit() else self.DEFAULT_TOP_NUM

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument("--top_num", type=str, help="Duration cost top count", default=cls.DEFAULT_TOP_NUM)

    def merge_func(self, mapper_res):
        # 过滤掉mapper_res中为None的元素
        mapper_res = list(filter(lambda df: df is not None, mapper_res))

        # 如果过滤后mapper_res为空，记录错误并返回
        if not mapper_res:
            logger.error("Mapper data is empty. Please check the input or data source.")
            return
        dataframes = [pd.DataFrame(item) for item in mapper_res]
        mapper_res = pd.concat(dataframes, ignore_index=True)
        # 从mapper_res中提取各个字段的值
        rank_id_arr = mapper_res["rankId"].values  # 提取rankId数组
        num_ranks = len(rank_id_arr)  # 获取rankId数组的长度
        group_name_arr = mapper_res["groupName"].values  # 提取groupName数组
        communication_time_arr = mapper_res["communicationTime"].values  # 提取通信时间数组
        op_name_arr = mapper_res["opName"].values  # 提取操作名称数组

        # 初始化用于存储分组信息的字典和数组
        process_group = defaultdict(lambda: defaultdict(list))  # 用于存储按组和操作名分组的索引
        transmit_time_arr = np.zeros(num_ranks, dtype=np.int64)  # 初始化传输时间数组
        related_ranks_arr = np.zeros(num_ranks, dtype=np.int32)  # 初始化相关rank数量数组

        # 遍历所有记录，按groupName和opName分组
        for idx in range(num_ranks):
            # 如果操作名称中包含"send"或"receive"，跳过（可能是发送或接收操作）
            if "send" in op_name_arr[idx] or "receive" in op_name_arr[idx]:
                continue
            # 将当前索引添加到对应的分组中
            process_group[group_name_arr[idx]][op_name_arr[idx]].append(idx)

        # 遍历分组后的数据，计算每个操作的传输时间和相关rank数量
        for _, ops_same_group in tqdm(process_group.items(), desc="Processing database data..."):
            for _, ops in ops_same_group.items():
                # 提取当前分组中所有操作的通信时间
                communication_time_list = [communication_time_arr[op_idx] for op_idx in ops]
                # 计算最小通信时间作为传输时间
                transmit_time = min(communication_time_list)
                # 计算当前分组中操作的数量作为相关rank数量
                related_ranks_num = len(ops)

                # 更新传输时间和相关rank数量数组
                for op_idx in ops:
                    transmit_time_arr[op_idx] = transmit_time
                    related_ranks_arr[op_idx] = related_ranks_num

        # 将计算得到的传输时间和相关rank数量添加到mapper_res中
        mapper_res.insert(mapper_res.shape[1], 'transmitTime', transmit_time_arr)
        mapper_res.insert(mapper_res.shape[1], 'relatedRanks', related_ranks_arr)

        # 调用过滤函数处理mapper_res
        self.filter_func(mapper_res)

    def filter_func(self, mapper_res):
        """
        处理数据，分组并检测异常值。
        """
        # 按 opType, dataSize, related_ranks 分组
        grouped = mapper_res.groupby(['opType', 'dataSize', 'relatedRanks'])

        for _, group in grouped:
            # 提取分组数据中的 transmit_time 列
            transmit_time_data = group['transmitTime'].values

            # 检测异常值
            outliers = detect_outliers_z_score(transmit_time_data)

            if outliers:
                # 如果存在异常值，将整个分组数据存入 Slow_Link_Ops
                self.slow_link_ops.append(group)

        if self.slow_link_ops:
            self.slow_link_ops = pd.concat(self.slow_link_ops, ignore_index=True)
            # 重置索引并去掉多余的索引列
            data = pd.DataFrame(self.slow_link_ops)

            # 按 'opType', 'dataSize', 'related_ranks' 分组
            grouped = data.groupby(['opType', 'dataSize', 'relatedRanks'])

            # 计算统计信息
            group_data = describe_duration(grouped['transmitTime'])

            # 找到每个组中 transmit_time 最小值和最大值对应的 rankId
            min_rank = grouped['transmitTime'].idxmin().map(data['rankId'])
            max_rank = grouped['transmitTime'].idxmax().map(data['rankId'])

            # 将最大值和最小值对应的 rankId 添加到 group_data
            group_data['maxRank'] = max_rank.values
            group_data['minRank'] = min_rank.values

            # 构造 filteringName
            group_data['opTypeRelatedRanksDataSize'] = group_data.index.map(lambda x: f"{x[0]}{x[2]}_{x[1]}")
            # 将 filteringName 移动到第一列
            cols = ['opTypeRelatedRanksDataSize'] + [col for col in group_data.columns if
                                                     col != 'opTypeRelatedRanksDataSize']
            group_data = group_data[cols]

            # 重置索引
            group_data = group_data.reset_index(drop=True)
            # 计算最大值和最小值与均值的绝对值
            group_data['abs_max_mean'] = abs(group_data['MaxNs'] - group_data['MeanNs'])
            group_data['abs_min_mean'] = abs(group_data['MinNs'] - group_data['MeanNs'])

            # 计算最大值和最小值与均值的绝对值中的较大值
            group_data['max_abs_mean'] = group_data[['abs_max_mean', 'abs_min_mean']].max(axis=1)

            # 计算偏移比值
            group_data['offsetRatio'] = group_data['max_abs_mean'] / group_data['StdNs']

            # 按偏移比值降序排序
            group_data = group_data.sort_values(by='offsetRatio', ascending=False)

            # 根据 self.top_num 筛选出偏移比值最大的前 N 条记录
            group_data = group_data.head(self.top_num)

            # 删除辅助列 'abs_max_mean', 'abs_min_mean', 'max_abs_mean'
            group_data = group_data.drop(columns=['abs_max_mean', 'abs_min_mean', 'max_abs_mean'])

            # 调整列的顺序，将 offsetRatio 移到 MinRank 和 MaxRank 之前
            columns = [col for col in group_data.columns if col not in ['maxRank', 'minRank', 'offsetRatio']]
            columns.insert(len(columns), 'offsetRatio')  # 将 offsetRatio 插入到倒数第三的位置
            columns.extend(['maxRank', 'minRank'])  # 添加 MaxRank 和 MinRank 到列的最后

            # 重新排列列的顺序
            group_data = group_data[columns]

            # 在处理 group_data 的最后部分并保存
            self.slow_link_sum = group_data

    def run(self, context):
        if self.top_num <= 0:
            logger.warning(f"SlowLink: top_num is set to a invalid value, "
                           f"it will be reset to default value({self.DEFAULT_TOP_NUM}).")
            self.top_num = self.DEFAULT_TOP_NUM
        mapper_res = self.mapper_func(context)
        self.merge_func(mapper_res)

        if self._export_type == "db":
            self.save_db()
        elif self._export_type == "notebook":
            self.save_notebook()
        else:
            logger.error("Unknown export type.")

    def save_notebook(self):
        self.dump_data(self.slow_link_sum, "slow_link_sum.csv", index=False)
        self.dump_data(self.slow_link_ops, "slow_link_ops.csv", index=False)
        self.create_notebook("stats.ipynb")
        self.add_helper_file("cluster_display.py")

    def save_db(self):
        self.dump_data(self.slow_link_sum, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_SLOW_LINK_SUM,
                       index=False)
        self.dump_data(self.slow_link_ops, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_SLOW_LINK_OPS,
                       index=False)

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        df = SlowLinkExport(profiler_db_path, analysis_class).read_export_db()
        if df is None or df.empty:
            logger.warning(f"There is no stats data in {profiler_db_path}.")
            return None
        df.insert(0, "rankId", rank_id)
        return df