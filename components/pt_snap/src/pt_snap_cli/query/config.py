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

"""Query configuration and template management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

_CALLSTACK_VARIANTS = ("v1", "v2")

# Field/template interpretation contract, independent of YAML ``version`` and
# SnapshotDB schema / callstack layout. v1/v2 SQL variants share one contract.
_OUTPUT_COLUMN_REQUIRED = ("column", "type")
OUTPUT_COLUMN_OPTIONAL = (
    "units",
    "metric_semantics",
    "scope",
    "denominator",
    "sentinel",
    "interpretation_limits",
)
_OUTPUT_COLUMN_KEYS = frozenset(_OUTPUT_COLUMN_REQUIRED + OUTPUT_COLUMN_OPTIONAL)
OUTPUT_SCHEMA_UNITS = frozenset({"bytes", "gib", "percent", "event_id", "count", "address", "flag", "text"})
OUTPUT_SCHEMA_METRIC_SEMANTICS = frozenset(
    {
        "instantaneous_occupancy",
        "same_event_gap",
        "share_of_included_rows",
        "identifier",
        "classification",
        "ordering_marker",
    }
)
OUTPUT_SCHEMA_SCOPES = frozenset({"dynamic", "static", "preexisting", "mixed", "captured_range", "same_event"})
_ENUM_FIELDS = {
    "units": OUTPUT_SCHEMA_UNITS,
    "metric_semantics": OUTPUT_SCHEMA_METRIC_SEMANTICS,
    "scope": OUTPUT_SCHEMA_SCOPES,
}


@dataclass
class QueryParameter:
    """Definition of a query parameter."""

    name: str
    type: str = "str"
    default: Any = None
    required: bool = False
    description: str = ""
    # Closed set of accepted values. Required for parameters that are rendered
    # into SQL as identifiers or keywords (e.g. ORDER BY column / direction),
    # where the type alone cannot bound what reaches the database.
    choices: Union[List[Any], None] = None

    def __post_init__(self) -> None:
        if self.choices is None:
            return
        if not isinstance(self.choices, list) or not self.choices:
            raise ValueError(f"Parameter '{self.name}' choices must be a non-empty list")
        if self.default is None:
            return
        matched = self._match_choice(self.default)
        if matched is None:
            raise ValueError(f"Parameter '{self.name}' default {self.default!r} is not one of its choices")
        self.default = matched

    def _match_choice(self, value: Any) -> Union[Any, None]:
        """Return the canonical choice equal to ``value``, or None when not allowed."""
        if self.choices is None:
            return value
        if self.type == "str" and isinstance(value, str):
            for choice in self.choices:
                if isinstance(choice, str) and choice.lower() == value.lower():
                    return choice
            return None
        return value if value in self.choices else None

    def validate(self, value: Any) -> Any:
        """Validate and convert parameter value.

        Args:
            value: Value to validate.

        Returns:
            Converted value. For ``str`` parameters with ``choices`` the
            canonical spelling from ``choices`` is returned, so case-insensitive
            input (``"desc"``) renders as declared (``"DESC"``).

        Raises:
            TypeError: If value cannot be converted to expected type.
            ValueError: If required parameter is missing or the value is not one
                of the declared choices.
        """
        if value is None:
            if self.required:
                raise ValueError(f"Required parameter '{self.name}' is missing")
            return self.default

        type_converters = {
            "str": str,
            "int": int,
            "float": float,
            "bool": lambda x: x.lower() in ("true", "1", "yes") if isinstance(x, str) else bool(x),
        }

        converter = type_converters.get(self.type, str)
        try:
            converted = converter(value)
        except (ValueError, TypeError) as e:
            raise TypeError(f"Parameter '{self.name}' cannot be converted to {self.type}: {e}") from e

        if self.choices is None:
            return converted
        matched = self._match_choice(converted)
        if matched is None:
            allowed = ", ".join(str(choice) for choice in self.choices)
            raise ValueError(f"Parameter '{self.name}' must be one of: {allowed} (got {value!r})")
        return matched


@dataclass
class QueryTemplate:
    """SQL query template definition."""

    name: str
    description: str = ""
    devices: List[str] = field(default_factory=lambda: ["all"])
    parameters: Dict[str, QueryParameter] = field(default_factory=dict)
    query: str = ""
    query_variants: Dict[str, str] = field(default_factory=dict)
    output_schema: List[Dict[str, Any]] = field(default_factory=list)
    category: str = "basic"
    # Interpretation contract for agents. Distinct from YAML ``version`` and
    # SnapshotDB schema / callstack layout; omitted on templates that have not
    # declared field semantics yet.
    semantics_version: Union[int, None] = None
    interpretation_limits: List[str] = field(default_factory=list)

    def sql_for_layout(self, layout: Union[str, None]) -> Union[str, None]:
        """Return SQL for a detected callstack layout.

        Templates without variants always use ``query``. Variant templates
        return the matching body, or ``None`` when the layout is missing or
        unknown.
        """
        if not self.query_variants:
            return self.query
        if layout is None:
            return None
        return self.query_variants.get(layout)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and convert parameters.

        Args:
            params: Parameter values.

        Returns:
            Validated and converted parameters.

        Raises:
            ValueError: If a required parameter is missing, a value is not one
                of the parameter's declared choices, or ``params`` contains a
                name the template does not declare. Unknown names are rejected
                rather than ignored so that a misspelled filter cannot silently
                widen a query.
            TypeError: If parameter type is invalid.
        """
        unknown = sorted(name for name in params if name not in self.parameters)
        if unknown:
            accepted = ", ".join(self.parameters) if self.parameters else "none"
            raise ValueError(
                f"Unknown parameter(s) for template '{self.name}': {', '.join(unknown)} (accepted: {accepted})"
            )

        validated = {}
        for name, param_def in self.parameters.items():
            value = params.get(name)
            validated[name] = param_def.validate(value)

        return validated

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_category: Union[str, None] = None) -> QueryTemplate:
        """Create QueryTemplate from dictionary.

        Args:
            data: Dictionary with template data.
            default_category: Category inferred from directory structure when
                not explicitly declared in the YAML.

        Returns:
            QueryTemplate instance.
        """
        parameters = {}
        for name, param_data in data.get("parameters", {}).items():
            parameters[name] = QueryParameter(
                name=name,
                type=param_data.get("type", "str"),
                default=param_data.get("default"),
                required=param_data.get("required", False),
                description=param_data.get("description", ""),
                choices=param_data.get("choices"),
            )

        template_name = data.get("name", "")
        query_variants = _parse_query_variants(template_name, data.get("query_variants"))
        explicit_query = data.get("query")
        if query_variants:
            if isinstance(explicit_query, str) and explicit_query.strip():
                raise ValueError(f"template '{template_name}' cannot declare both query and query_variants")
            query = query_variants.get("v2") or ""
        else:
            query = explicit_query or ""

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            devices=data.get("devices", ["all"]),
            parameters=parameters,
            query=query,
            query_variants=query_variants,
            output_schema=_parse_output_schema(template_name, data.get("output_schema")),
            category=data.get("category") or default_category or "basic",
            semantics_version=_parse_semantics_version(template_name, data.get("semantics_version")),
            interpretation_limits=_parse_interpretation_limits(
                f"template '{template_name}'", data.get("interpretation_limits")
            ),
        )


def _parse_semantics_version(template_name: str, raw: Any) -> Union[int, None]:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(f"semantics_version for '{template_name}' must be a positive integer, got {raw!r}")
    return raw


def _parse_interpretation_limits(label: str, raw: Any) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"interpretation_limits for {label} must be a non-empty list of strings")
    limits: List[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"interpretation_limits[{index}] for {label} must be a non-empty string")
        limits.append(item.strip())
    return limits


def _parse_output_schema(template_name: str, raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"output_schema for '{template_name}' must be a list of column mappings")

    columns: List[Dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"output_schema[{index}] for '{template_name}' must be a mapping with column and type")
        unknown = set(item) - _OUTPUT_COLUMN_KEYS
        if unknown:
            raise ValueError(
                f"output_schema[{index}] for '{template_name}' has unsupported keys: "
                f"{', '.join(sorted(str(key) for key in unknown))}"
            )
        column = item.get("column")
        column_type = item.get("type")
        if not isinstance(column, str) or not column.strip():
            raise ValueError(f"output_schema[{index}] for '{template_name}' must declare a non-empty column name")
        if not isinstance(column_type, str) or not column_type.strip():
            raise ValueError(
                f"output_schema[{index}] column '{column}' for '{template_name}' must declare a non-empty type"
            )

        parsed: Dict[str, Any] = {"column": column, "type": column_type}
        for key in OUTPUT_COLUMN_OPTIONAL:
            if key not in item:
                continue
            value = item[key]
            if key == "interpretation_limits":
                parsed[key] = _parse_interpretation_limits(f"'{template_name}' column '{column}'", value)
                continue
            if key == "sentinel":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(
                        f"output_schema column '{column}' for '{template_name}' "
                        f"sentinel must be an integer, got {value!r}"
                    )
                parsed[key] = value
                continue
            if key == "denominator":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"output_schema column '{column}' for '{template_name}' denominator must be a non-empty string"
                    )
                parsed[key] = value.strip()
                continue
            allowed = _ENUM_FIELDS[key]
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(
                    f"output_schema column '{column}' for '{template_name}' {key} "
                    f"must be one of: {', '.join(sorted(allowed))} (got {value!r})"
                )
            parsed[key] = value
        columns.append(parsed)
    return columns


def _parse_query_variants(template_name: str, raw: Any) -> Dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"query_variants for '{template_name}' must be a mapping of layout to SQL")
    if not raw:
        return {}

    unknown = set(raw) - set(_CALLSTACK_VARIANTS)
    if unknown:
        raise ValueError(
            f"query_variants for '{template_name}' has unsupported layouts: "
            f"{', '.join(sorted(str(key) for key in unknown))}"
        )
    missing = [name for name in _CALLSTACK_VARIANTS if name not in raw]
    if missing:
        raise ValueError(
            f"query_variants for '{template_name}' must include {_CALLSTACK_VARIANTS}, missing: {', '.join(missing)}"
        )

    variants: Dict[str, str] = {}
    for name in _CALLSTACK_VARIANTS:
        sql = raw[name]
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"query_variants.{name} for '{template_name}' must be a SQL string")
        variants[name] = sql
    return variants


@dataclass
class QueryConfig:
    """Query configuration containing multiple templates."""

    version: str = "1.0"
    queries: Dict[str, QueryTemplate] = field(default_factory=dict)

    def get_query(self, name: str) -> Union[QueryTemplate, None]:
        """Get a query template by name.

        Args:
            name: Template name.

        Returns:
            QueryTemplate or None if not found.
        """
        return self.queries.get(name)

    def list_queries(self) -> List[str]:
        """List all available query names.

        Returns:
            List of query names.
        """
        return list(self.queries.keys())

    @classmethod
    def load_yaml(cls, path: Union[str, Path], default_category: Union[str, None] = None) -> QueryConfig:
        """Load configuration from YAML file.

        Args:
            path: Path to YAML file.
            default_category: Category inferred from directory structure when
                not explicitly declared in the YAML.

        Returns:
            QueryConfig instance.

        Raises:
            FileNotFoundError: If file does not exist.
            yaml.YAMLError: If YAML is invalid.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        queries = {}
        for name, query_data in data.get("queries", {}).items():
            query_data["name"] = name
            queries[name] = QueryTemplate.from_dict(query_data, default_category=default_category)

        return cls(
            version=data.get("version", "1.0"),
            queries=queries,
        )

    @classmethod
    def load_yaml_from_string(cls, content: str) -> QueryConfig:
        """Load configuration from YAML string.

        Args:
            content: YAML content string.

        Returns:
            QueryConfig instance.
        """
        data = yaml.safe_load(content) or {}

        queries = {}
        for name, query_data in data.get("queries", {}).items():
            query_data["name"] = name
            queries[name] = QueryTemplate.from_dict(query_data)

        return cls(
            version=data.get("version", "1.0"),
            queries=queries,
        )
