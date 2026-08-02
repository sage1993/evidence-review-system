"""Canonical Python namespace for the evidence review runtime.

The implementation remains physically stored under ``ansim_review`` during the
compatibility window. A meta-path alias maps canonical submodule imports to the
same legacy module objects, preventing duplicate class identities while new
entrypoints and integrations migrate to ``evidence_review``.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Sequence
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from importlib.resources.abc import ResourceReader
from types import ModuleType
from typing import Final

CANONICAL_PACKAGE: Final = "evidence_review"
_LEGACY_PACKAGE: Final = "ansim_review"
_LOCAL_MODULES: Final = frozenset(
    {
        f"{CANONICAL_PACKAGE}.cli",
        f"{CANONICAL_PACKAGE}.__main__",
    }
)
_FINDER_MARKER: Final = "_evidence_review_legacy_alias_finder"


class _LegacyAliasLoader(Loader):
    """Return a legacy module and expose its resources through the alias."""

    def __init__(
        self,
        module: ModuleType,
        legacy_name: str,
        legacy_loader: Loader | None,
    ) -> None:
        self._module = module
        self._legacy_name = legacy_name
        self._legacy_loader = legacy_loader

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        return self._module

    def exec_module(self, module: ModuleType) -> None:
        return None

    def get_resource_reader(self, fullname: str) -> ResourceReader | None:
        """Delegate canonical resource access to the physical legacy package."""
        if self._legacy_loader is None:
            return None
        get_reader = getattr(self._legacy_loader, "get_resource_reader", None)
        if not callable(get_reader):
            return None
        reader = get_reader(self._legacy_name)
        return reader if isinstance(reader, ResourceReader) else None


class _LegacyAliasFinder(MetaPathFinder):
    """Resolve ``evidence_review.*`` to the identical ``ansim_review.*`` module."""

    _evidence_review_legacy_alias_finder = True

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        prefix = f"{CANONICAL_PACKAGE}."
        if not fullname.startswith(prefix) or fullname in _LOCAL_MODULES:
            return None

        legacy_name = f"{_LEGACY_PACKAGE}.{fullname.removeprefix(prefix)}"
        legacy_spec = importlib.util.find_spec(legacy_name)
        if legacy_spec is None:
            return None

        module = importlib.import_module(legacy_name)
        return ModuleSpec(
            fullname,
            _LegacyAliasLoader(module, legacy_name, legacy_spec.loader),
            origin=legacy_spec.origin,
            is_package=legacy_spec.submodule_search_locations is not None,
        )


if not any(getattr(finder, _FINDER_MARKER, False) for finder in sys.meta_path):
    sys.meta_path.insert(0, _LegacyAliasFinder())
