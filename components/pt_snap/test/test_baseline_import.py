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

import pytest

from benchmarks.baseline_import import _max_rss_kb, _parse_resource_output


def test_parse_resource_output_ignores_other_stderr_lines():
    metrics = _parse_resource_output("warning\nPT_SNAP_RESOURCE user=1.25 sys=0.5 max_rss_kb=2048.0\n")

    assert metrics == {"user_s": 1.25, "sys_s": 0.5, "max_rss_kb": 2048.0}


def test_parse_resource_output_rejects_missing_metrics():
    with pytest.raises(RuntimeError, match="did not report"):
        _parse_resource_output("warning only")

    with pytest.raises(RuntimeError, match="invalid benchmark resource output"):
        _parse_resource_output("PT_SNAP_RESOURCE user=1.25 max_rss_kb=2048")


def test_max_rss_kb_normalizes_darwin_bytes_and_keeps_linux_kibibytes():
    assert _max_rss_kb(2 * 1024 * 1024, "darwin") == 2048
    assert _max_rss_kb(2048, "linux") == 2048
