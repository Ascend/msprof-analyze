# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_exports.summary_export import ApiStatisticExport, KernelDetailsExport

logger = get_logger()


class ExportSummary(BaseRecipeAnalysis):
    def __init__(self, params):
        super().__init__(params)
        logger.info("ExportSummary init.")

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)

    def reducer_func(self, mapper_res):
        mapper_res = [
            data for data in mapper_res if data is not None and any(df is not None and not df.empty for df in data[1:])
        ]
        if not mapper_res:
            logger.error("Mapper data is None.")
            return
        for rank_id, api_df, kernel_df in mapper_res:
            ascend_output_path = self._get_ascend_output_path(rank_id)
            if not ascend_output_path:
                logger.warning("Cannot find ASCEND_PROFILER_OUTPUT for rank %s", rank_id)
                continue
            self._save_api_statistic(rank_id, api_df, ascend_output_path)
            self._save_kernel_details(rank_id, kernel_df, ascend_output_path)

    def _get_ascend_output_path(self, rank_id):
        rank_path = self._data_map.get(rank_id, "")
        ascend_output = os.path.join(rank_path, Constant.SINGLE_OUTPUT)
        if os.path.exists(ascend_output):
            return ascend_output
        return None

    def _save_api_statistic(self, rank_id, df, ascend_output_path):
        if df is None or df.empty:
            logger.warning("No API statistic data for rank %s", rank_id)
            return
        api_statistic_path = os.path.join(ascend_output_path, Constant.API_STATISTIC_CSV)
        if os.path.exists(api_statistic_path):
            logger.info("%s already exists for rank %s, skip generation.", api_statistic_path, rank_id)
            return
        FileManager.create_csv_from_dataframe(api_statistic_path, df, index=False)
        logger.info("Generated %s for rank %s", api_statistic_path, rank_id)

    def _save_kernel_details(self, rank_id, df, ascend_output_path):
        if df is None or df.empty:
            logger.warning("No kernel details data for rank %s", rank_id)
            return
        kernel_details_path = os.path.join(ascend_output_path, Constant.KERNEL_DETAILS_CSV)
        if os.path.exists(kernel_details_path):
            logger.info("%s already exists for rank %s, skip generation.", kernel_details_path, rank_id)
            return
        FileManager.create_csv_from_dataframe(kernel_details_path, df, index=False)
        logger.info("Generated %s for rank %s", kernel_details_path, rank_id)

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        if not profiler_db_path:
            return None, None, None

        api_df = ApiStatisticExport(profiler_db_path, analysis_class).read_export_db()
        kernel_df = KernelDetailsExport(profiler_db_path, analysis_class).read_export_db()

        if (api_df is None or api_df.empty) and (kernel_df is None or kernel_df.empty):
            logger.warning("There is no summary data in %s.", profiler_db_path)
            return None, None, None

        return rank_id, api_df, kernel_df
