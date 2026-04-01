#!/usr/bin/python
# -*- coding: utf-8 -*-
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

import pandas as pd
import numpy as np
import difflib
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()

class Comparator:
    def __init__(self, df_gpu: pd.DataFrame,
                 df_npu: pd.DataFrame,
                 ):
        self.df_gpu = df_gpu
        self.df_npu = df_npu

    @staticmethod
    def get_best_fuzzy_match(key, candidates, threshold=0.8):
        if not candidates:
            return None
        matches = difflib.get_close_matches(key, candidates, n=1, cutoff=threshold)
        return matches[0] if matches else None

    def compare(self, enable_fuzzy=True, fuzzy_threshold=0.6):
        df_gpu, df_npu = self.df_gpu, self.df_npu

        # 初始化匹配键
        df_gpu['match_key'] = df_gpu['Parent Module'].fillna('').astype(str) + '/' + df_gpu['Module'].astype(str)
        df_npu['match_key'] = df_npu['Parent Module'].fillna('').astype(str) + '/' + df_npu['Module'].astype(str)
        df_npu['match_key'] = df_npu['match_key'].str.replace('Ascend', '', regex=False)
        df_npu['Match Type'] = 'rule'

        # 模糊匹配
        if enable_fuzzy:
            gpu_keys_set = set(df_gpu['match_key'])
            unmatched_mask = ~df_npu['match_key'].isin(gpu_keys_set)
            unmatched_npu_keys = df_npu.loc[unmatched_mask, 'match_key'].unique()
            candidate_keys = list(gpu_keys_set)

            match_map = {}
            for n_key in unmatched_npu_keys:
                best_match = self.get_best_fuzzy_match(n_key, candidate_keys, threshold=fuzzy_threshold)
                if best_match:
                    match_map[n_key] = best_match

            rows_to_update = df_npu['match_key'].isin(match_map.keys())
            df_npu.loc[rows_to_update, 'Match Type'] = 'fuzzy'
            df_npu.loc[rows_to_update, 'match_key'] = df_npu.loc[rows_to_update, 'match_key'].map(match_map)

        df_gpu = df_gpu.sort_values(['match_key', 'Total Kernel Duration(us)'], ascending=[True, False])
        df_npu = df_npu.sort_values(['match_key', 'Total Kernel Duration(us)'], ascending=[True, False])

        df_gpu['row_id'] = df_gpu.groupby('match_key').cumcount()
        df_npu['row_id'] = df_npu.groupby('match_key').cumcount()

        merge_keys = ['match_key', 'row_id']

        gpu_rename_map = {col: f'(GPU) {col}' for col in df_gpu.columns if col not in merge_keys}
        npu_rename_map = {col: f'(NPU) {col}' for col in df_npu.columns if col not in merge_keys + ['Match Type']}
        df_gpu = df_gpu.rename(columns=gpu_rename_map)
        df_npu = df_npu.rename(columns=npu_rename_map)

        df_merged = pd.merge(
            df_gpu,
            df_npu,
            on=merge_keys,
            how='outer'
        )

        split_keys = df_merged['match_key'].str.rsplit('/', n=1, expand=True)

        for prefix in ['(GPU) ', '(NPU) ']:
            col_parent = f'{prefix}Parent Module'
            col_module = f'{prefix}Module'
            
            if col_parent not in df_merged.columns:
                df_merged[col_parent] = np.nan
            if col_module not in df_merged.columns:
                df_merged[col_module] = np.nan

            df_merged[col_parent] = df_merged[col_parent].fillna(split_keys[0])
            df_merged[col_module] = df_merged[col_module].fillna(split_keys[1])
        
        df_merged.drop(columns=['row_id'], inplace=True)

        # 计算耗时占比：Duration / sum(Duration)，增加非零防护
        gpu_total_sum = df_merged['(GPU) Total Kernel Duration(us)'].sum()
        npu_total_sum = df_merged['(NPU) Total Kernel Duration(us)'].sum()
        df_merged['(GPU) Total Kernel Duration(%)'] = np.where(
            gpu_total_sum != 0,
            df_merged['(GPU) Total Kernel Duration(us)'] / gpu_total_sum * 100,
            np.nan
        )
        df_merged['(NPU) Total Kernel Duration(%)'] = np.where(
            npu_total_sum != 0,
            df_merged['(NPU) Total Kernel Duration(us)'] / npu_total_sum * 100,
            np.nan
        )

        # 格式化百分比显示
        df_merged['(GPU) Total Kernel Duration(%)'] = df_merged['(GPU) Total Kernel Duration(%)'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else ' ')
        df_merged['(NPU) Total Kernel Duration(%)'] = df_merged['(NPU) Total Kernel Duration(%)'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else ' ')

        # 计算 Module 层级的耗时比率：NPU / GPU
        gpu_module_sum = df_gpu.groupby('match_key')['(GPU) Total Kernel Duration(us)'].sum()
        npu_module_sum = df_npu.groupby('match_key')['(NPU) Total Kernel Duration(us)'].sum()

        # 计算 Ratio
        module_ratio = npu_module_sum / gpu_module_sum.where(gpu_module_sum != 0, np.nan)

        # 计算 diff
        module_diff = npu_module_sum - gpu_module_sum

        # 映射回 merged dataframe
        df_merged['(NPU/GPU) Module Time Ratio'] = df_merged['match_key'].map(module_ratio)
        df_merged['(NPU-GPU,us) Module Time Diff'] = df_merged['match_key'].map(module_diff)
        df_merged['(NPU/GPU) Module Time Ratio'] = df_merged['(NPU/GPU) Module Time Ratio'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else ' ')

        match_cols = ['(GPU) Parent Module', '(GPU) Module', '(NPU) Parent Module', '(NPU) Module', 'Match Type']
        cols = match_cols + [
            '(NPU) Op Name', '(NPU) Op Count', '(NPU) Kernel List',
            '(NPU) Total Kernel Duration(us)', '(NPU) Total Kernel Duration(%)', '(NPU) Avg Kernel Duration(us)',
            '(GPU) Op Name', '(GPU) Op Count', '(GPU) Kernel List',
            '(GPU) Total Kernel Duration(us)', '(GPU) Total Kernel Duration(%)', '(GPU) Avg Kernel Duration(us)',
            '(NPU/GPU) Module Time Ratio', '(NPU-GPU,us) Module Time Diff'
        ]
        final_cols = [c for c in cols if c in df_merged.columns]

        for c in match_cols:
            if c not in df_merged.columns:
                df_merged[c] = np.nan
        df_merged = df_merged.fillna(' ')

        df_merged_final = df_merged[final_cols].sort_values(
            ['(GPU) Parent Module', '(NPU-GPU,us) Module Time Diff', '(GPU) Total Kernel Duration(us)'],
            ascending=[True, False, False]
        ).reset_index(drop=True)

        return df_merged_final
