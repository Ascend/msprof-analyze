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

import time

from pt_snap_cli.snapshot.util.timer import timer


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


def test_timer_reports_to_logger():
    logger = FakeLogger()

    @timer(name="unit-work", logger=logger)
    def work():
        time.sleep(0.001)
        return 123

    result = work()

    assert result == 123
    assert len(logger.messages) == 1
    assert logger.messages[0].startswith("unit-work took ")


def test_timer_without_logger_prints(capsys):
    @timer()
    def work():
        return "done"

    result = work()
    captured = capsys.readouterr()

    assert result == "done"
    assert "work took " in captured.out
