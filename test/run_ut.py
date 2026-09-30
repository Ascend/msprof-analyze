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
import logging
import os
import shutil
import subprocess
import sys


def set_python_path():
    msprof_analyze_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Update PYTHONPATH
    python_path = os.environ.get("PYTHONPATH", "")
    if not python_path:
        python_path += msprof_analyze_root
    else:
        python_path += f":{msprof_analyze_root}"
    os.environ["PYTHONPATH"] = python_path


def run_ut():
    cur_dir = os.path.realpath(os.path.dirname(__file__))
    top_dir = os.path.realpath(os.path.dirname(cur_dir))
    ut_path = os.path.join(cur_dir, "ut/")
    src_dir = top_dir
    report_dir = os.path.join(cur_dir, "report")

    if os.path.exists(report_dir):
        shutil.rmtree(report_dir)

    os.makedirs(report_dir)

    cmd = ["python3", "-m", "pytest", ut_path, "--junitxml=" + os.path.join(report_dir, "final.xml"),
           "--cov=" + src_dir, "--cov-branch", "--cov-report=xml:" + os.path.join(report_dir, "coverage.xml")]

    result_ut = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    while result_ut.poll() is None:
        line = result_ut.stdout.readline().strip()
        if line:
            logging.info(line)

    ut_status = False
    if result_ut.returncode == 0:
        ut_status = True
        logging.info("run ut successfully.")
    else:
        logging.error("run ut failed.")

    return ut_status

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    set_python_path()
    ut_success = run_ut()
    if ut_success:
        sys.exit(0)
    else:
        sys.exit(1)
