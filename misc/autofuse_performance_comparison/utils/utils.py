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
import subprocess  # nosec B404
import sys
from typing import List
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


def subprocess_cmd(cmd: List[str]) -> bool:
    if not isinstance(cmd, list) or not cmd:
        logger.error("Invalid command: %s", cmd)
        return False
    logger.info("Execute command: %s", ' '.join(cmd))
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            logger.error("Command execute failed! return code: %s", result.returncode)
            return False
        else:
            return True
    except Exception as err:
        logger.error("Command execute failed, error: %s", str(err))
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="Autofuse Performance Comparison")
    parser.add_argument(
        "-f", "--whole_graph", type=str, required=True, help="The JSON file converted from ge_proto_xxxx_Build.txt"
    )
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
