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
import subprocess
import sys
from typing import List
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


def subprocess_cmd(cmd: List[str]) -> bool:
    if not isinstance(cmd, list) or not cmd:
        logger.error(f"Invalid command: {cmd}")
        return False
    logger.info(f"Execute command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error(f"Command execute failed! return code: {result.returncode}")
            return False
        else:
            return True
    except Exception as err:
        logger.error(f"Command execute failed, error: {str(err)}")
        return False

def parse_args():
    parser = argparse.ArgumentParser(description="Autofuse Performance Comparison")
    parser.add_argument("-f", "--whole_graph", type=str, required=True,
                        help="The JSON file converted from ge_proto_xxxx_Build.txt")
    parser.add_argument("-d", "--subgraph_dir", type=str, required=True, help="Path of subgraph directory")
    parser.add_argument("-p", "--dump_path", type=str, required=True, help="Path of datadump")
    parser.add_argument("-o", "--output_path", type=str, default=os.getcwd(), help="Path of comparison result")
    args = parser.parse_args()
    PathManager.check_input_file_path(args.whole_graph)
    PathManager.check_input_directory_path(args.subgraph_dir)
    PathManager.check_input_directory_path(args.dump_path)
    if not os.path.exists(args.output_path):
        PathManager.make_dir_safety(args.output_path)
    PathManager.check_output_directory_path(args.output_path)
    return args
