# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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


def build_version_text() -> str:
    try:
        from msprof_analyze import __buildinfo__ as _buildinfo
    except ImportError:
        return ""
    build_date = getattr(_buildinfo, 'BUILD_DATE', '') or ''
    copyright_year = 'unknown'
    if build_date:
        copyright_year = build_date[:4]  # 业务保证
    lines = [
        "msprof-analyze {} ({})".format(
            getattr(_buildinfo, 'VERSION', 'UNKNOWN'), getattr(_buildinfo, 'COMMIT', 'unknown')
        ),
        "Copyright (C) {} Huawei Technologies Co., Ltd.".format(copyright_year),
        "License: Mulan PSL v2.",
        "",
        "Build Info:",
        "  Date : {}".format(build_date or 'unknown'),
        "  Repo : {}".format(getattr(_buildinfo, 'REPO', 'unknown')),
    ]
    return "\n".join(lines) + "\n"
