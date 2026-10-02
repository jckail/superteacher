"""Every third-party module the app imports at runtime must be declared in requirements.txt.

requirements-dev.txt adds test-only packages (httpx used to be one), so a missing runtime dependency passes the unit
tests and then crashes the production image on import. This test fails first.
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# import name -> distribution name, where they differ
DIST = {"pydantic_settings": "pydantic-settings", "yaml": "pyyaml"}
# Always installed alongside a declared package (fastapi -> starlette + pydantic); importing them directly is fine.
TRANSITIVE = {"starlette", "pydantic", "typing_extensions", "anyio"}


def declared() -> set[str]:
    names = set()
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.add(re.split(r"[\[<>=!~ ;]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def imported_modules() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in (ROOT / "superteacher").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for m in mods:
                found.setdefault(m.split(".")[0], str(path.relative_to(ROOT)))
    return found


def test_runtime_imports_are_declared_in_requirements_txt():
    reqs = declared()
    missing = {}
    for mod, where in imported_modules().items():
        if mod in sys.stdlib_module_names or mod in {"superteacher", "alembic"} - reqs or mod in TRANSITIVE:
            continue
        if DIST.get(mod, mod).lower().replace("_", "-") not in reqs:
            missing[mod] = where
    assert not missing, f"imported by the app but missing from requirements.txt: {missing}"


def test_httpx_is_a_declared_runtime_dependency():
    assert "httpx" in declared()  # superteacher/mailer.py sends mail with it
