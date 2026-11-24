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

"""Generate new CLI exports from the adjacent inspectable synthetic JSON only.

No external pickle, original producer, GUI, network or hardware is used. The
pickle is built locally from primitive JSON values, not supplied by a third party.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name("three_shard_free_requested.json")
FORMATS = ("msinsight", "pt-snap-native-v2")


def import_source(source: Path, output_format: str, home: Path) -> dict:
    """Exercise the real CLI entry point in a subprocess with isolated focus."""
    env = os.environ.copy()
    env.pop("PT_SNAP_DB_PATH", None)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pt_snap_cli.cli",
            "import",
            str(source),
            "--format",
            output_format,
            "--events-per-slice",
            "1",
            "--device",
            "0",
            "--no-focus",
            "--json",
        ],
        cwd=home,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(f"CLI import failed ({result.returncode}): {result.stderr}{result.stdout}")
    return json.loads(result.stdout)


def write_source(directory: Path, data: dict) -> Path:
    """Serialize only caller-constructed synthetic data to a NEW local file."""
    path = directory / "three_shard_free_requested.pkl"
    with path.open("xb") as stream:
        pickle.dump(data, stream, protocol=4)
    return path


def generate(output: Path) -> dict:
    """Keep the generated source adjacent to its v1 GUI cache; never replace."""
    output = output.absolute()
    output.mkdir()
    source = write_source(output, json.loads(SOURCE.read_text(encoding="utf-8")))
    exports = {fmt: import_source(source, fmt, output) for fmt in FORMATS}
    return {"source": str(source), "exports": exports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New, absent output directory")
    args = parser.parse_args()
    print(json.dumps(generate(args.output), indent=2))


if __name__ == "__main__":
    main()
