"""Guard rails for how the code is layered, so refactors don't quietly undo it."""

import ast
import asyncio
from pathlib import Path

from superteacher.routers import ai as ai_router

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


def test_turn_limit_is_one_semaphore_per_event_loop():
    async def twice():
        return ai_router._turn_limit(), ai_router._turn_limit()

    a1, a2 = asyncio.run(twice())
    b1, _ = asyncio.run(twice())
    assert a1 is a2  # stable within a loop
    assert a1 is not b1  # never shared across loops
