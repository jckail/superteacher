"""Guard rails for how the code is layered, so refactors don't quietly undo it."""

import ast
import asyncio
from pathlib import Path

import pytest

from superteacher import ai_capacity
from superteacher.config import get_settings

PKG = Path(__file__).resolve().parent.parent / "superteacher"


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            found.add(("." * node.level) + (node.module or ""))
            found.update(("." * node.level) + (node.module or "") + "." + a.name for a in node.names)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
    return found


def test_services_never_import_routers():
    """Routers sit on top. Shared query code lives in superteacher/queries.py, not in a router."""
    offenders = {
        p.name: sorted(i for i in _imports(p) if i.startswith(".routers") or i.startswith("superteacher.routers"))
        for p in PKG.glob("*.py")
        if p.name != "main.py"  # main is the composition root: it wires the routers together
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_ai_capacity_is_shared_within_loop_and_independent_across_loops(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_requests", 1)

    async def occupy():
        lease = ai_capacity.acquire()
        with pytest.raises(ai_capacity.CapacityError):
            ai_capacity.acquire()
        return lease

    first = asyncio.run(occupy())
    try:
        # A lease held by the first loop cannot consume another worker/loop's budget.
        second = asyncio.run(occupy())
        second.release()
    finally:
        first.release()
