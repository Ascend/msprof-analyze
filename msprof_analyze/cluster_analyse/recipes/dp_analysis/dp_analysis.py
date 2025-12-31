# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
import json

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.dp_analysis_export import MstxDPMarkExport, MstxRangeExport
from msprof_analyze.cluster_analyse.recipes.cluster_display import DPAnalysisDisplay

logger = get_logger()


def process_marker_data(mark_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract the msg field containing JSON strings and parse them into separate columns.
    msg: {"running_reqs":1,"waiting_reqs":0,"gpu_cache_usage":0.0,"out_tokens":16}
    """
    if 'msg' not in mark_df.columns:
        logger.error("No 'msg' column found in marker data.")
        raise ValueError("No 'msg' column found in marker data.")
    # Parse each JSON string into key-value pairs
    parsed_data = []
    for idx, row in enumerate(mark_df.itertuples(index=False)):
        try:
            msg_json = json.loads(row.msg)
            parsed_data.append(msg_json)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON in row {idx}: {e}")

    # Convert the parsed data into DataFrame and merge it with the original DataFrame
    if parsed_data:
        parsed_df = pd.DataFrame(parsed_data)
        mark_df = pd.concat([mark_df.reset_index(drop=True), parsed_df], axis=1)

    return mark_df


def process_range_data(range_df: pd.DataFrame) -> pd.DataFrame:
    """Preprocess range data by adding time-related columns."""
    ns_to_ms = Constant.NS_TO_US * Constant.US_TO_MS
    range_df['start_time_ms'] = range_df['cann_start_ts'] / ns_to_ms
    range_df['end_time_ms'] = range_df['cann_end_ts'] / ns_to_ms
    range_df['duration_ms'] = range_df['end_time_ms'] - range_df['start_time_ms']
    return range_df


def format_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Format column names and filter the DataFrame to keep only target columns."""
    rename_columns = {
        'tid_range': 'Tid',
        'rank_id': 'RankId',
        'step_id': 'StepId',
        'start_time_ms': 'StartTimeMs',
        'end_time_ms': 'EndTimeMs',
        'duration_ms': 'DurationMs',
        'running_reqs': 'RunningReqs',
        'waiting_reqs': 'WaitingReqs',
        'gpu_cache_usage': 'GPUCacheUsage',
        'out_tokens': 'OutTokens',
    }
    target_columns = list(rename_columns.keys())
    filtered_df = df[target_columns].copy()
    formated_df = filtered_df.rename(rename_columns, axis='columns')
    return formated_df


class DPAnalysis(BaseRecipeAnalysis):
    '''DP analysis class'''
    #save db name
    TABLE_DB_NAME = "DPAnalysis"
    #save files name
    EVENT_SUMMARY_FILE = "dp_event_summary.csv"
    EVENT_PLOTS_FILE = "dp_event_plot.png"
    EVENT_SUBPLOTS_FILE = "dp_event_subplots.png"
    
    def __init__(self, params):
        super().__init__(params)
        logger.info("DPAnalysis init")
        self.dp_events = None
    
    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))
    
    def run(self, context):
        '''main entry point of the analysis'''
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)
        if self.dp_events is None or self.dp_events.empty:
            logger.error("No DP events data to save.")
            raise ValueError("No DP events data to save.")
        self.generate_dp_plots()
        self.generate_dp_subplots()
        self.get_summary_csv()
        if self._export_type == Constant.DB:
            self.save_db()
        else:
            logger.error(f"Unknown export type: {self._export_type}")
    
    def reducer_func(self, mapper_res):
        '''reducer function'''
        if not mapper_res:
            logger.error("No data from mapper to reducer.")
            return
        mapper_res = list(filter(lambda x: x is not None, mapper_res))
        if not mapper_res:
            logger.error("All data from mapper are None after filtering.")
            return
        self.dp_events = pd.concat(mapper_res)
    
    def parse_dp_mstx_events(self, profiler_db_path, analysis_class, rank_id):
        '''parse dp mstx events from db'''
        # export marker data
        mark_df = MstxDPMarkExport(profiler_db_path, analysis_class).read_export_db()
        # export range data
        range_df = MstxRangeExport(profiler_db_path, analysis_class).read_export_db()
        
        if mark_df is None or mark_df.empty:
            logger.error(f"No marker data found for rank {rank_id}.")
            raise ValueError("Marker data is required for DP analysis.")
        
        if range_df is None or range_df.empty:
            logger.error(f"No range data found for rank {rank_id}.")
            raise ValueError("Range data is required for DP analysis.")

        if len(mark_df) != len(range_df):
            logger.error(f"Marker and range data length mismatch for rank {rank_id}.")
            raise ValueError("Marker and range data length must be equal.")
        
        # process and merge data
        range_df_id = range_df.copy()
        range_df_id['rank_id'] = rank_id
        range_df_id['step_id'] = range_df_id.index
        processed_range_df = process_range_data(range_df_id)
        processed_mark_df = process_marker_data(mark_df)
        
        # merge processed range and marker DataFrames on index for duplicate columns
        suffixes = ('_marker', '_range')
        merged_df = pd.merge(
            processed_range_df,
            processed_mark_df, 
            left_index=True, 
            right_index=True, 
            how='inner', 
            suffixes=suffixes
            )
        if len(merged_df) != len(processed_range_df) or len(merged_df) != len(processed_mark_df):
            logger.warning(f"Data loss during merge for rank {rank_id}. "
                f"Original: {len(processed_range_df)}, Merged: {len(merged_df)}")
        
        # format columns    
        formatted_df = format_columns(merged_df)
        return formatted_df
    
    def save_db(self):
        '''save analysis results to db'''
        self.dump_data(self.dp_events, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_DB_NAME)
        logger.info(f"DP events data saved to table {self.TABLE_DB_NAME} in database.")
    
    def generate_dp_plots(self):
        '''generate dp analysis plots'''
        output_path = os.path.join(self.output_path, self.EVENT_PLOTS_FILE)
        DPAnalysisDisplay(self.dp_events).plot_out_tokens_step(output_path)
        logger.info(f"DP event plots saved to {output_path}.")
    
    def generate_dp_subplots(self):
        '''generate dp analysis subplots'''
        output_path = os.path.join(self.output_path, self.EVENT_SUBPLOTS_FILE)
        DPAnalysisDisplay(self.dp_events).plot_rank_subplots(output_path, ncols=1)
        logger.info(f"DP event subplots saved to {output_path}.")
    
    def get_summary_csv(self):
        '''get summary csv path'''
        output_path = os.path.join(self.output_path, self.EVENT_SUMMARY_FILE)
        self.dump_data(self.dp_events, output_path, index=False)
        logger.info(f"DP event summary CSV saved to {output_path}.")
    
    def _mapper_func(self, data_map, analysis_class):
        '''collect data from a single rank'''
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        mapper_res = self.parse_dp_mstx_events(profiler_db_path, analysis_class, rank_id)
        return mapper_res