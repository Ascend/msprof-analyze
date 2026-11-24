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
import subprocess
import sys
import threading
import time

# 当前ci环境不支持该用例
BLACKLIST_FILES = ["test_cann_api_sum.py"]
# 模块顺序仅用于兜底：优先按 SLOW_CASES 入槽，其余用例按此顺序
ST_MODULES = ["compare_tools", "advisor", "cluster_analyse"]
# 2026-11-20 PreSmoke（run 147，4 并发槽位）实测各用例耗时，单位秒，供更新 SLOW_CASES 与排查慢用例时参考：
# compare_tools：operator_compare 70.3、communication_compare 62.6、api_compare 62.3、
#                vs_npu 59.6、vs_npu_step 28.1、db_npu_vs_npu 20.9、profiling 17.9、
#                memory_compare 16.8、kernel_compare 4.3、mindspore 1.0
# advisor：pt_compare 202.7、pt_db_compare 22.0
# cluster_analyse：pytorch_text 37.6、pytorch_db 11.7、compute_op_sum 10.4、hccl_sum 5.4、
#                  step_id_param 4.5、msprof_db 1.0、mindspore_db 1.0
# 耗时超过 30s 的用例优先入槽，避免长尾用例过晚启动；仅影响调度顺序，
# 未知用例按 ST_MODULES 顺序排在后面，更新时保持从长到短即可
SLOW_CASES = [
    "advisor/test_advisor_cmd_single_ascend_pt_compare.py",
    "compare_tools/test_compare_tools_cmd_pytorch_npu_npu_enable_operator_compare.py",
    "compare_tools/test_compare_tools_cmd_pytorch_npu_npu_enable_api_compare.py",
    "compare_tools/test_compare_tools_cmd_pytorch_npu_vs_npu.py",
    "compare_tools/test_compare_tools_cmd_pytorch_npu_npu_enable_communication_compare.py",
    "cluster_analyse/test_cluster_analyse_pytorch_text.py",
]
# 并发槽位数：实测 4 个已贴近最慢单用例耗时，再增加只带来争抢开销
PARALLEL = 4
POLL_INTERVAL_SECONDS = 0.2
# 等待子进程退出和日志线程收尾的上限，避免极端场景下超时兜底失效
STOP_GRACE_SECONDS = 30
TIMEOUT_SECONDS = 3600


def print_stout(output, task_name):
    with output:
        for line in output:
            line = line.rstrip()
            if not line:
                continue
            logging.info("[%s] %s", task_name, line)


def collect_st_tasks(st_root):
    tasks = []
    for module in ST_MODULES:
        module_path = os.path.join(st_root, module)
        if not os.path.isdir(module_path):
            continue
        for file_name in sorted(os.listdir(module_path)):
            if not file_name.startswith("test_") or not file_name.endswith(".py"):
                continue
            if file_name in BLACKLIST_FILES:
                continue
            tasks.append({
                "name": "%s/%s" % (module, file_name),
                "path": os.path.join(module_path, file_name),
            })
    priority = {name: index for index, name in enumerate(SLOW_CASES)}
    tasks.sort(key=lambda task: priority.get(task["name"], len(SLOW_CASES)))
    return tasks


def start_st_task(task):
    cmd = ["python3", "-m", "pytest", "-s", task["path"]]
    process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    stout_thread = threading.Thread(target=print_stout, args=(process.stdout, task["name"]), daemon=True)
    stout_thread.start()
    logging.info("start st case %s.", task["name"])
    return process, stout_thread


def join_stout_thread(stout_thread):
    stout_thread.join(timeout=STOP_GRACE_SECONDS)
    if stout_thread.is_alive():
        logging.warning("st log thread is still alive after %d seconds.", STOP_GRACE_SECONDS)


def stop_st_processes(running_processes):
    for process in running_processes:
        if process.poll() is None:
            process.terminate()
    for process, (_, stout_thread) in running_processes.items():
        try:
            process.wait(timeout=STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        join_stout_thread(stout_thread)


def run_st():
    st_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "st")
    pending_tasks = collect_st_tasks(st_root)
    if not pending_tasks:
        logging.error("no st case found.")
        return False
    parallel = min(PARALLEL, len(pending_tasks))
    logging.info("run %d st cases with parallel %d.", len(pending_tasks), parallel)

    running_processes = {}
    start_time = time.monotonic()
    while pending_tasks or running_processes:
        if time.monotonic() - start_time >= TIMEOUT_SECONDS:
            logging.error("run st use case timeout.")
            stop_st_processes(running_processes)
            return False
        while pending_tasks and len(running_processes) < parallel:
            task = pending_tasks.pop(0)
            process, stout_thread = start_st_task(task)
            running_processes[process] = (task, stout_thread)
        for process in list(running_processes):
            if process.poll() is None:
                continue
            task, stout_thread = running_processes.pop(process)
            join_stout_thread(stout_thread)
            if process.returncode != 0:
                logging.error("st case %s failed.", task["name"])
                stop_st_processes(running_processes)
                return False
            logging.info("st case %s passed.", task["name"])
        if pending_tasks or running_processes:
            time.sleep(POLL_INTERVAL_SECONDS)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    st_success = run_st()
    if st_success:
        logging.info("run st successfully.")
        sys.exit(0)
    else:
        logging.error("run st failed.")
        sys.exit(1)
