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

"""Shell completion functions for CLI options."""

from __future__ import annotations

import json
import os
from contextlib import closing
from pathlib import Path
from typing import List, Union

from pt_snap_cli.config import DB_PATH_KEY, Config


def complete_template_names() -> List[str]:
    """Return all registered query template names for shell completion."""
    from pt_snap_cli.query.registry import list_queries

    return sorted(list_queries())


def complete_categories() -> List[str]:
    """Return valid category names from template directory structure for shell completion."""
    from pt_snap_cli.query.registry import discover_categories

    return discover_categories()


def _resolve_db_for_completion() -> Union[Path, None]:
    """Resolve the database path using the same priority as the CLI.

    Priority: env var > project focus > global config.
    """
    env_path = os.environ.get("PT_SNAP_DB_PATH")
    if env_path:
        return Path(env_path).expanduser()

    project_focus = Config.find_project_focus_path()
    if project_focus:
        try:
            with open(project_focus, encoding="utf-8") as f:
                data = json.load(f)
            db_path = data.get(DB_PATH_KEY) or data.get("current_db_path")
            if db_path:
                return Path(db_path).expanduser()
        except (json.JSONDecodeError, OSError):
            pass

    global_path = Config().current_db_path
    return global_path


def complete_device_ids() -> List[str]:
    """Return device IDs from the resolved database for shell completion."""
    import sqlite3

    db_path = _resolve_db_for_completion()
    if db_path is None or not db_path.exists():
        return []

    try:
        from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver

        devices = DatasetResolver().completion_device_ids(db_path)
        if devices is not None:
            return [str(device) for device in devices]
        uri = f"file:{db_path}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trace_entry_%'")
            device_ids = []
            for row in cursor.fetchall():
                table_name = row[0]
                device_id = table_name.split("_")[-1]
                device_ids.append(device_id)
            return sorted(device_ids, key=int)
    except Exception:
        return []
