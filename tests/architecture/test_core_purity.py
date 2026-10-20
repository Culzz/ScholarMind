"""Structural guardrails for the codebase.

The core package must stay framework-free: it may not import FastAPI, SQLAlchemy
sessions, Celery, or an LLM vendor SDK. This keeps retrieval, eligibility,
evaluation and citation validation independently testable and prevents the
provider from leaking into domain logic.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE_PACKAGE = ROOT / "scholarmind"

FORBIDDEN_ROOTS = {
    "fastapi",
    "sqlalchemy",
    "celery",
    "redis",
    "anthropic",
    "openai",
    "httpx",
    "alembic",
    "pydantic_settings",
}

FORBIDDEN_EXCEPTIONS: dict[str, set[str]] = {
    # The evaluation harness may report cost/latency; it still may not import a
    # web framework or a database session.
    "evaluation": {"sqlalchemy", "fastapi"},
    # Ingestion is the boundary layer: fetching is its job, so an HTTP client
    # is permitted there (and only there).
    "ingestion": {"httpx"},
}


def iter_core_modules() -> list[Path]:
    return sorted(path for path in CORE_PACKAGE.rglob("*.py"))


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import inside the core package
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.architecture
def test_core_package_exists() -> None:
    assert CORE_PACKAGE.exists(), "the core package directory is missing"


@pytest.mark.architecture
@pytest.mark.parametrize("module", iter_core_modules(), ids=lambda p: p.name)
def test_core_modules_do_not_import_frameworks(module: Path) -> None:
    relative = module.relative_to(CORE_PACKAGE)
    top = relative.parts[0] if len(relative.parts) > 1 else ""
    allowed = FORBIDDEN_EXCEPTIONS.get(top, set())
    offending = (imported_roots(module) & FORBIDDEN_ROOTS) - allowed
    assert not offending, f"{relative} imports forbidden module(s): {sorted(offending)}"


@pytest.mark.architecture
def test_core_package_has_no_side_effect_imports() -> None:
    """Core modules must not execute network or database work at import time."""
    for module in iter_core_modules():
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                name = getattr(func, "attr", getattr(func, "id", ""))
                assert name not in {"create_engine", "connect", "run"}, (
                    f"{module.name} performs a side effect at import time: {name}()"
                )


@pytest.mark.architecture
def test_api_package_exists() -> None:
    assert (ROOT / "services" / "api" / "app" / "main.py").exists()
