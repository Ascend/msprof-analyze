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

from __future__ import annotations

from typing import Any, Dict, Union

from pt_snap_cli import __version__
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.models import CapabilityCatalog


class CapabilityService:
    """Read-only catalog of CLI version and template contracts."""

    def __init__(
        self,
        query_service: Union[QueryService, None] = None,
    ) -> None:
        self._query_service = query_service or QueryService()

    def catalog(self) -> CapabilityCatalog:
        return CapabilityCatalog(
            cli_version=__version__,
            templates=self._query_service.list_template_contracts(),
        )

    def catalog_to_dict(self, catalog: CapabilityCatalog) -> Dict[str, Any]:
        return {
            "cli_version": catalog.cli_version,
            "templates": [self._query_service.template_info_to_dict(info) for info in catalog.templates],
        }
