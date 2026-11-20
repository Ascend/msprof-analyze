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

from pathlib import Path
from unittest.mock import patch

import pytest

from pt_snap_cli.core.analysis.capability_service import CapabilityService
from pt_snap_cli.query.registry import QueryRegistry


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path):
        QueryRegistry.reset()
        yield
        QueryRegistry.reset()


def test_catalog_includes_version_template_contracts() -> None:
    catalog = CapabilityService().catalog()
    payload = CapabilityService().catalog_to_dict(catalog)

    assert payload["cli_version"] == catalog.cli_version
    names = {item["name"] for item in payload["templates"]}
    assert {"leak_detection", "preexisting_live", "freed_block_lifetime"} <= names
    leak = next(item for item in payload["templates"] if item["name"] == "leak_detection")
    assert leak["semantics_version"] == 1
    assert "min_size" in leak["parameters"]
    assert "device_id" not in leak["parameters"]
    assert set(payload) == {"cli_version", "templates"}
