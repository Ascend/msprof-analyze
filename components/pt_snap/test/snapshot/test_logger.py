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

import logging
from pathlib import Path

import pytest

from pt_snap_cli.snapshot.util import logger as logger_module


@pytest.fixture(autouse=True)
def reset_global_logger_state():
    original_file = logger_module._global_log_file
    original_handler = logger_module._global_file_handler
    logger_module._global_log_file = None
    logger_module._global_file_handler = None
    yield
    if logger_module._global_file_handler is not None:
        logger_module._global_file_handler.close()
    logger_module._global_log_file = original_file
    logger_module._global_file_handler = original_handler


def test_get_logger_basic():
    logger = logger_module.get_logger("snapshot_test_basic")

    assert logger.name == "snapshot_test_basic"
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)


def test_get_logger_with_custom_level():
    logger = logger_module.get_logger("snapshot_test_level", level=logging.DEBUG)

    assert logger.level == logging.DEBUG
    assert logger.handlers[0].level == logging.DEBUG


def test_set_global_log_file(tmp_path: Path):
    log_file = tmp_path / "test.log"
    logger_module.set_global_log_file(str(log_file))

    logger = logger_module.get_logger("snapshot_test_global")

    assert len(logger.handlers) == 2
    file_handler = next(handler for handler in logger.handlers if isinstance(handler, logging.FileHandler))
    assert file_handler.baseFilename == str(log_file.absolute())


def test_set_global_log_file_nonexistent_directory(tmp_path: Path):
    with pytest.raises(OSError):
        logger_module.set_global_log_file(str(tmp_path / "nonexistent" / "test.log"))


def test_set_global_log_file_not_directory(tmp_path: Path):
    not_directory = tmp_path / "not_dir.txt"
    not_directory.write_text("", encoding="utf-8")

    with pytest.raises(OSError):
        logger_module.set_global_log_file(str(not_directory / "test.log"))


def test_logger_output_to_file(tmp_path: Path):
    log_file = tmp_path / "test.log"
    logger_module.set_global_log_file(str(log_file))
    logger = logger_module.get_logger("snapshot_test_output")

    logger.info("Test log message")
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()

    assert "Test log message" in log_file.read_text(encoding="utf-8")


def test_attach_file_handler_to_existing_loggers(tmp_path: Path):
    logger = logger_module.get_logger("snapshot_test_existing")

    logger_module.set_global_log_file(str(tmp_path / "test.log"))

    assert len(logger.handlers) == 2
    assert sum(isinstance(handler, logging.FileHandler) for handler in logger.handlers) == 1


def test_multiple_loggers_share_file_handler(tmp_path: Path):
    log_file = tmp_path / "test.log"
    logger_module.set_global_log_file(str(log_file))
    logger_one = logger_module.get_logger("snapshot_test_one")
    logger_two = logger_module.get_logger("snapshot_test_two")

    for logger in (logger_one, logger_two):
        assert sum(isinstance(handler, logging.FileHandler) for handler in logger.handlers) == 1

    logger_one.info("Message from module1")
    logger_two.info("Message from module2")
    logger_module._global_file_handler.flush()
    log_content = log_file.read_text(encoding="utf-8")
    assert "Message from module1" in log_content
    assert "Message from module2" in log_content
