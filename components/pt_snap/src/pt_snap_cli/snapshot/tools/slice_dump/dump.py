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

import os.path
from pathlib import Path
from typing import List, cast

from typing_extensions import Literal

from ...representation import load_snapshot_representation, replay_snapshot
from ...util import get_logger
from .hooker import SliceDumpHooker

dump_logger = get_logger("DUMP")


def run_slice_dump(
    snapshot_file: str,
    device: int = 0,
    slices: int = 4,
    max_entries: int = 15000,
    dump_dir: str = "",
    dump_type: Literal["json", "pkl"] = "pkl",
):
    resolved_dump_dir = dump_dir or os.path.dirname(snapshot_file)
    dump_logger.info("Start to dump snapshot slice, reading pickle file '%s'.", snapshot_file)
    df = load_snapshot_representation(Path(snapshot_file), "pickle")
    if "segments" not in df or "device_traces" not in df or not df["device_traces"]:
        dump_logger.warning(
            "Snapshot files with no event records cannot be replayed or split. You may have disabled "
            "history event recoding during collection."
        )
        return
    # These are the sequence fields of the snapshot format; no values are coerced.
    traces = cast(List[List[object]], df["device_traces"])
    segments = cast(List[object], df["segments"])
    if device < 0 or len(traces) <= device or not traces[device]:
        dump_logger.warning('The snapshot file did not record any event data for the specified device %s.', device)
        return
    dump_logger.info('Start loading snapshot with %s segments, %s events', len(segments), len(traces[device]))
    dump_logger.info("Successfully loaded snapshot, starting to replay and dump.")
    slice_dump_hooker = SliceDumpHooker(
        dump_dir=resolved_dump_dir,
        num_of_slices=slices,
        max_entries=max_entries,
        dump_type=dump_type,
    )
    _, _ = replay_snapshot(df, device, hooker=slice_dump_hooker)
    dump_logger.info("Successfully replay and dump snapshot.")
