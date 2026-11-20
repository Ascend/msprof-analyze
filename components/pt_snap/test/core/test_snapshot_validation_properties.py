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

"""Trusted in-memory numeric metadata rejection through the real import boundary.

Only the representation-loading seam is replaced: no pickle is created or
unpickled, and conversion, validation, error normalization and cleanup stay real.
Missing keys and arbitrary structural/type errors are a separate runtime gap;
this module covers the existing controlled ValueError conversion contract.
"""

from __future__ import annotations

import copy
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pt_snap_cli.core.common.errors import ImportExecutionError
from pt_snap_cli.core.importing.snapshot_import_backend import SnapshotImportBackend

PROPERTY_SETTINGS = settings(max_examples=25, derandomize=True, database=None, deadline=None, print_blob=True)


@pytest.mark.parametrize("field", ["addr", "size", "stream", "device_free", "id"])
@PROPERTY_SETTINGS
@given(suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 +-", max_size=40))
def test_generated_bad_numeric_snapshot_values_reject_without_publication(field: str, suffix: str) -> None:
    event = {"action": "alloc", "addr": 4096, "size": 1, "stream": 0, "frames": []}
    event[field] = f"not-an-integer:{suffix}"
    representation = {"segments": [], "device_traces": [[event]]}
    before = copy.deepcopy(representation)

    with TemporaryDirectory() as directory, pytest.MonkeyPatch.context() as monkeypatch:
        root = Path(directory)
        source = root / "trusted-in-memory.pkl"
        source_bytes = b"inert test placeholder; the representation loader must be replaced"
        source.write_bytes(source_bytes)
        output = root / "output"
        output.mkdir()
        backend = SnapshotImportBackend()
        destination = backend.target_db_path(source, output)
        destination.write_bytes(b"previous database must survive validation failure")
        previous = destination.read_bytes()
        loads = []

        def load_representation(path: Path) -> dict[str, object]:
            assert path == source
            loads.append(path)
            return representation

        # The lazy-import test removes this module from sys.modules. Resolve
        # the current object here, not a stale reference captured at collection.
        snapshot2db = importlib.import_module("pt_snap_cli.snapshot.tools.adaptors.snapshot2db")
        monkeypatch.setattr(snapshot2db, "load_snapshot_representation", load_representation)
        with pytest.raises(ImportExecutionError, match="Snapshot import backend failed") as error:
            backend.dump_to_db(source, output, device=0)

        assert isinstance(error.value.__cause__, ValueError)
        assert loads == [source]
        assert representation == before
        assert source.read_bytes() == source_bytes
        assert destination.read_bytes() == previous
        assert list(output.iterdir()) == [destination]
