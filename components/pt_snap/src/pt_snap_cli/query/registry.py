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

"""Query registry for managing predefined queries."""

from __future__ import annotations

import copy
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Union

from pt_snap_cli.query.config import QueryConfig, QueryTemplate

QueryFactory = Callable[[], QueryTemplate]


class QueryRegistry:
    """Registry for predefined query templates."""

    _instance: Union[QueryRegistry, None] = None
    # Initialized in __new__ (the singleton has no __init__ so repeated
    # QueryRegistry() calls cannot wipe the shared state).
    _queries: Dict[str, QueryTemplate]  # pyright: ignore[reportUninitializedInstanceVariable]
    _factories: Dict[str, QueryFactory]  # pyright: ignore[reportUninitializedInstanceVariable]

    def __new__(cls) -> QueryRegistry:
        """Singleton pattern for global registry."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._queries = {}
            instance._factories = {}
            cls._instance = instance
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    def register(self, template: QueryTemplate) -> None:
        """Register a query template.

        Args:
            template: Template to register.
        """
        self._queries[template.name] = template

    def register_factory(self, name: str, factory: QueryFactory) -> None:
        """Register a factory function for lazy template creation.

        Args:
            name: Template name.
            factory: Factory function that returns QueryTemplate.
        """
        self._factories[name] = factory

    def get(self, name: str) -> Union[QueryTemplate, None]:
        """Get a registered template by name.

        Args:
            name: Template name.

        Returns:
            QueryTemplate or None if not found.
        """
        if name in self._queries:
            return self._queries[name]

        if name in self._factories:
            template = self._factories[name]()
            self._queries[name] = template
            return template

        return None

    def list_queries(self) -> List[str]:
        """List all registered query names.

        Returns:
            List of query names.
        """
        return list(set(self._queries.keys()) | set(self._factories.keys()))

    def list_queries_with_details(self) -> List[Dict[str, str]]:
        """List all registered queries with details.

        Returns:
            List of dicts with name and description.
        """
        details = []
        all_names = set(self._queries.keys()) | set(self._factories.keys())

        for name in sorted(all_names):
            template = self.get(name)
            if template:
                details.append(
                    {
                        "name": name,
                        "description": template.description,
                    }
                )

        return details

    def list_by_category(self, category: str) -> List[str]:
        """List query names filtered by category.

        Args:
            category: Category to filter by (basic, statistical, business).

        Returns:
            Sorted list of query names in the given category.
        """
        all_names = set(self._queries.keys()) | set(self._factories.keys())
        result = []
        for name in sorted(all_names):
            template = self.get(name)
            if template and template.category == category:
                result.append(name)
        return result

    def list_by_category_with_details(self, category: str) -> List[Dict[str, str]]:
        """List queries filtered by category with details.

        Args:
            category: Category to filter by (basic, statistical, business).

        Returns:
            List of dicts with name and description for the given category.
        """
        details = []
        for name in self.list_by_category(category):
            template = self.get(name)
            if template:
                details.append(
                    {
                        "name": name,
                        "description": template.description,
                    }
                )
        return details

    def unregister(self, name: str) -> bool:
        """Unregister a query template.

        Args:
            name: Template name to remove.

        Returns:
            True if template was removed.
        """
        removed = False
        if name in self._queries:
            del self._queries[name]
            removed = True
        if name in self._factories:
            del self._factories[name]
            removed = True
        return removed


_registry = QueryRegistry()


def register_query(template: QueryTemplate) -> None:
    """Register a query template in the global registry.

    Args:
        template: Template to register.
    """
    _registry.register(template)


def get_query(name: str) -> Union[QueryTemplate, None]:
    """Get a query template from the global registry.

    Args:
        name: Template name.

    Returns:
        QueryTemplate or None if not found.
    """
    return _registry.get(name)


def get_template_info(name: str) -> Union[Dict[str, Any], None]:
    """Get detailed information about a template.

    Args:
        name: Template name.

    Returns:
        Dictionary with template details or None if not found.
    """
    template = _registry.get(name)
    if not template:
        return None

    return {
        "name": template.name,
        "description": template.description,
        "devices": template.devices,
        "parameters": {
            param_name: {
                "type": param.type,
                "default": param.default,
                "required": param.required,
                "description": param.description,
                "choices": param.choices,
            }
            for param_name, param in template.parameters.items()
        },
        "output_schema": template.output_schema,
        "semantics_version": template.semantics_version,
        "interpretation_limits": template.interpretation_limits,
        "query": template.query,
    }


def list_queries() -> List[str]:
    """List all registered queries.

    Returns:
        List of query names.
    """
    return _registry.list_queries()


def list_queries_with_details() -> List[Dict[str, str]]:
    """List all registered queries with details.

    Returns:
        List of dicts with name, description, devices, and parameters.
    """
    return _registry.list_queries_with_details()


def list_by_category(category: str) -> List[str]:
    """List query names filtered by category.

    Args:
        category: Category to filter by (basic, statistical, business).

    Returns:
        Sorted list of query names in the given category.
    """
    return _registry.list_by_category(category)


def list_by_category_with_details(category: str) -> List[Dict[str, str]]:
    """List queries filtered by category with details.

    Args:
        category: Category to filter by (basic, statistical, business).

    Returns:
        List of dicts with name and description for the given category.
    """
    return _registry.list_by_category_with_details(category)


def get_template_dir() -> Path:
    """Return the path to the template directory."""
    return Path(__file__).parent / "templates"


def discover_categories(template_dir: Union[Union[Path, str], None] = None) -> List[str]:
    """Discover category names from subdirectory structure.

    Args:
        template_dir: Path to template directory. Defaults to package templates dir.

    Returns:
        Sorted list of category names (subdirectory names).
    """
    if template_dir is None:
        template_dir = get_template_dir()
    else:
        template_dir = Path(template_dir)

    if not template_dir.exists():
        return []

    return sorted(
        d.name
        for d in template_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
    )


def _infer_category(yaml_file: Path, template_dir: Path) -> Union[str, None]:
    """Infer category from the parent directory of a YAML file.

    Returns None when the file is directly under the template root
    (not in a subdirectory), letting YAML's own category field or
    default take precedence.
    """
    try:
        parent = yaml_file.resolve().parent.name
        template_root = template_dir.resolve().name
        if parent != template_root:
            return parent
    except OSError:
        pass
    return None


def _load_yaml_templates(template_dir: Union[Union[Path, str], None] = None) -> None:
    """Load all YAML templates from the template directory.

    Scans recursively (``**/*.yaml``) so that each subdirectory
    acts as a category.  The subdirectory name is used as the
    template's category when the YAML does not declare one.

    Args:
        template_dir: Path to template directory. Defaults to package templates dir.
    """
    if template_dir is None:
        template_dir = Path(__file__).parent / "templates"
    else:
        template_dir = Path(template_dir)

    if not template_dir.exists():
        return

    for yaml_file in sorted(template_dir.glob("**/*.yaml")):
        try:
            default_cat = _infer_category(yaml_file, template_dir)
            config = QueryConfig.load_yaml(yaml_file, default_category=default_cat)
            for _query_name, template in config.queries.items():
                _registry.register(template)
        except Exception as e:
            warnings.warn(f"Failed to load query template from {yaml_file}: {e}", stacklevel=2)


_packaged: Dict[str, Tuple[QueryTemplate, QueryTemplate]] = {}


def is_packaged_query(name: str) -> bool:
    """Only unchanged, actually loaded packaged objects have global semantics.

    A runtime override, even with a built-in name or identical SQL, is custom.
    Retain a deep copy too, since QueryTemplate is mutable.
    """
    current = get_query(name)
    original = _packaged.get(name)
    return original is not None and current is original[0] and current == original[1]


def _load_all_templates() -> None:
    """Load all templates from YAML files and record their actual identities."""
    _load_yaml_templates()
    _packaged.clear()
    for name in list_queries():
        template = get_query(name)
        if template is not None:
            _packaged[name] = (template, copy.deepcopy(template))


try:
    _load_all_templates()
except Exception as e:
    warnings.warn(f"Failed to load query templates: {e}", stacklevel=2)
