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
    parser.add_argument('-o', "--output_path", type=str, default=os.getcwd(),
                        help="Path of comparison result")
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
    logger.info(f'The comparison task has been completed in a total time of {end_time - start_time}')
