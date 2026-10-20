#!/bin/bash
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

set -e

# 获取脚本的绝对路径和目录
real_path=$(readlink -f "$0")
script_dir=$(dirname "$real_path")
output_dir="${script_dir}/ut_coverage"
root_path=$(readlink -f "${script_dir}/..")
msprof_analyze_path="${root_path}/msprof_analyze"
srccode="${msprof_analyze_path}/advisor,${msprof_analyze_path}/cli,${msprof_analyze_path}/cluster_analyse,${msprof_analyze_path}/compare_tools,${msprof_analyze_path}/prof_common,${msprof_analyze_path}/prof_exports"
test_code="${script_dir}/ut"

# 更新 PYTHONPATH
export PYTHONPATH="${root_path}:${test_code}:${PYTHONPATH}"

# 创建输出目录
umask 022
mkdir -p "$output_dir"
cd "$output_dir"

# 删除旧的覆盖率文件
rm -f .coverage

# 运行单元测试并生成覆盖率报告
coverage run --branch --source="${srccode}" -m pytest -s "${test_code}" --junit-xml=./final.xml
coverage xml -o coverage.xml
coverage report >python_coverage_report.log

# 如果设置了 diff 参数，比较覆盖率差异
if [[ -n "$1" && "$1" == "diff" ]]; then
  target_branch=${2:-master}
  diff-cover coverage.xml --compare-branch="origin/${target_branch}" --html-report inc_coverage_result.html --fail-under=80
fi

# 输出报告路径
echo "Report: $output_dir"

# 清理 .pycache 文件
find "${script_dir}/.." -name "__pycache__" -exec rm -r {} +
