# Copyright (c) 2024, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


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
