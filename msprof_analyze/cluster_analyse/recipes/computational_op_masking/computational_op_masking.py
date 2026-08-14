# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

# pylint: disable=duplicate-code

import os
import argparse
import pandas as pd

from typing import List, Tuple

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.context import ConcurrentContext
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.cluster_analyse.common_func.linearity_utils import LinearityUtils

logger = get_logger()


class RetDataFrames:
    def __init__(self, step_df, communication_df, computation_df):
        self.step_df = step_df
        self.communication_df = communication_df
        self.computation_df = computation_df


class ComputationalOpMasking(BaseRecipeAnalysis):
    PARALLEL_INPUT_NAME = "parallel_types"
    PARALLEL_COL_NAME = "parallelType"
    STEP_LINEARITY = "step_linearity"
    # 使用共享工具类的列名定义
    Computational_Operator_Linearity_COLUMNS = LinearityUtils.COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS
    parallel_types = [("dp", "edp"), ("edp",), ("dp",), ("ep",), ("pp",), ("mp",), ("tp",)]
    step_columns = ["id", "startNs", "endNs"]

    def __init__(self, params):
        super().__init__(params)
        self.linearity_ret = pd.DataFrame()
        self.params = params
        self.db_paths = self._get_rank_db()

        # 从 params 中获取 parallel_types（更健壮的方式）
        parallel_types_arg = self._extra_args.get(self.PARALLEL_INPUT_NAME)
        if parallel_types_arg is not None:
            # 转换为元组列表
            if isinstance(parallel_types_arg, list) and len(parallel_types_arg) > 0:
                if isinstance(parallel_types_arg[0], (list, tuple)):
                    self.parallel_types = [tuple(item) for item in parallel_types_arg]
                else:
                    self.parallel_types = parallel_types_arg

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument(
            "--parallel_types",
            type=cls.parse_parallel_type,
            default=cls.parallel_types,
            help=(
                "Parallel strategy groups. Format: 'a;b,c;d,e,f' (NO trailing semicolon). "
                "Each group: 1+ comma-separated names. Example:'dp;mp,tp'.Default: %(default)s"
            ),
        )
        BaseRecipeAnalysis.add_parser_argument(parser)

    @staticmethod
    def parse_parallel_type(value: str) -> List[Tuple[str, ...]]:
        """
        Parse a string like "a;b,c;d,e,f" into[('a',), ('b','c'), ('d','e','f')].
        Rules:
            -Groups are separated by ';'
            -Items within a group are separated by ','
            -Empty input returns []
            -Empty groups (e.g. "a;;b") are ignored (not an error)**
            -Whitespace around items is stripped
        """
        if not value or not value.strip():
            return []
        groups = []
        for i, group_str in enumerate(value.split(";")):
            group_str = group_str.strip()
            if not group_str:
                raise argparse.ArgumentTypeError(f"Empty group at position ({i + 1} (input: '{value}')")
            items = [item.strip() for item in group_str.split(",")]
            if any(not item for item in items):
                raise argparse.ArgumentTypeError(f"Empty item in group (after filtering empty groups): '{group_str}'")
            groups.append(tuple(items))
        return groups

    def aggregate_stats(self, context: ConcurrentContext):
        def safe_concat(key: str) -> pd.DataFrame:
            futures = context.future_dict.get(key, [])
            df_list = [future.result() for future in futures]
            valid_dfs = [df for df in df_list if df is not None and not df.empty]
            return pd.concat(valid_dfs, ignore_index=True) if valid_dfs else pd.DataFrame()

        # Get each DataFrame
        step_time_df = safe_concat(ComputationalOpMasking.STEP_LINEARITY)
        return step_time_df

    def mapper_func(self, context: ConcurrentContext):
        for db_map in self.db_paths:
            context.submit(self.STEP_LINEARITY, self.get_linearity_df, db_map, self._recipe_name)

    def run(self, context: ConcurrentContext):
        self.mapper_func(context)
        context.wait_all_futures()
        self.linearity_ret = self.aggregate_stats(context)
        if self.linearity_ret.empty:
            logger.warning("No data available for linearity analysis.")
            return
        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error("Unknown export type.")

    def save_db(self):
        self.dump_data(
            data=self.linearity_ret,
            file_name=Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
            table_name=Constant.TABLE_COMPUTATIONAL_OPERATOR_MASKING_LINEARITY,
            index=False,
        )

    def save_csv(self):
        self.dump_data(data=self.linearity_ret, file_name="computational_operator_masking_linearity.csv", index=False)

    def get_linearity_df(self, data_map, analysis_class) -> pd.DataFrame:
        """
        Compute the linearity of communication operators.
        使用共享工具类实现

        Args:
            data_map: 数据源映射
            analysis_class: 分析类名

        Returns:
            A DataFrame containing the linearity results, or None if no data is available.
        """
        target_step_id = self._step_id if self._step_id != -1 else None
        return LinearityUtils.compute_linearity_df(
            data_map=data_map,
            analysis_class=analysis_class,
            parallel_types=self.parallel_types,
            step_columns=self.step_columns,
            parallel_col_name=self.PARALLEL_COL_NAME,
            target_step_id=target_step_id,
            use_merge=True,  # computational_op_masking 需要合并通信区间
        )
