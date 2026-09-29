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
import os
import re
import shutil
import shlex
from subprocess import Popen, PIPE


def delete_file(pattern, work_path):
    file_list = os.listdir(work_path)
    for file_name in file_list:
        if re.match(pattern, file_name):

            os.remove(os.path.join(work_path, file_name))


def recover_env(work_path="./"):
    if os.path.exists("./log"):
        shutil.rmtree("./log")

    if os.path.exists("./tune_ops_file.cfg"):
        os.remove("./tune_ops_file.cfg")

    delete_file(r"ma_advisor_+", work_path)


def run_command(cmd):
    # Make sure the process output can be displayed on the console
    p = Popen(shlex.split(cmd, posix=False), stdout=PIPE, bufsize=0, universal_newlines=False)
    p.wait()
