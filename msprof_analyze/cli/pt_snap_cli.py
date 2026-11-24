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

"""Route the complete embedded snapshot CLI without changing its argument contract."""

import sys

import click


def run_pt_snap(arguments):
    from pt_snap_cli.cli import _safe_call

    return _safe_call(list(arguments), prog_name="msprof-analyze pt-snap")


class PtSnapCommand(click.Command):
    """Forward every token, including --, to the snapshot parser exactly once."""

    def parse_args(self, ctx, args):
        ctx.params["arguments"] = list(args)
        ctx.args = []
        return []

    def invoke(self, ctx):
        ctx.exit(run_pt_snap(ctx.params["arguments"]))


pt_snap_command = PtSnapCommand(
    name="pt-snap",
    help="Import, split, query and report PyTorch memory snapshots (Python 3.7.5+).",
    add_help_option=False,
)


def main():
    # Snapshot analysis must not import the existing pandas/advisor/cluster stack
    # or print banners into the snapshot JSON/error streams.
    if len(sys.argv) > 1 and sys.argv[1] == "pt-snap":
        return run_pt_snap(sys.argv[2:])
    # Delayed import avoids loading the legacy stack for snapshot commands.
    # pylint: disable-next=cyclic-import
    from msprof_analyze.cli.entrance import msprof_analyze_cli

    # Click's decorator exposes a Command with a variadic __call__ interface.
    # pylint: disable-next=no-value-for-parameter
    return msprof_analyze_cli()


if __name__ == "__main__":
    sys.exit(main())
