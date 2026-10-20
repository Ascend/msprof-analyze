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
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from misc.inductor_triton_performance_comparison.comparison_generator import ComparisonGenerator
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


def main():
    parser = argparse.ArgumentParser(description="Inductor Triton Performance Comparison")
    parser.add_argument("-d", "--fx_graph_path", type=str, required=True, help="Path of fx graph")
    parser.add_argument('-o', "--output_path", type=str, default=os.getcwd(), help="Path of comparison result")
    args = parser.parse_args()
    PathManager.check_input_directory_path(args.fx_graph_path)
    if not os.path.exists(args.output_path):
        PathManager.make_dir_safety(args.output_path)
    PathManager.check_output_directory_path(args.output_path)
    ComparisonGenerator(args).run()


if __name__ == "__main__":
    start_time = datetime.now(timezone.utc)
    main()
    end_time = datetime.now(timezone.utc)
    logger.info('The comparison task has been completed in a total time of %s', end_time - start_time)
