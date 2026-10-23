"""Every third-party module the app imports at runtime must be declared in requirements.txt.

requirements-dev.txt adds test-only packages (httpx used to be one), so a missing runtime dependency passes the unit
tests and then crashes the production image on import. This test fails first.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent

# import name -> distribution name, where they differ
DIST = {"agents": "openai-agents", "pydantic_settings": "pydantic-settings", "yaml": "pyyaml"}
# Always installed alongside a declared package (fastapi -> starlette + pydantic); importing them directly is fine.
TRANSITIVE = {"starlette", "pydantic", "typing_extensions", "anyio"}


def declared() -> set[str]:
    return {canonicalize_name(req.name) for req in _requirements((ROOT / "requirements.txt").read_text())}


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


def test_calendar_and_postgresql_runtime_dependencies_remain_declared():
    assert {"tzdata", "psycopg"} <= declared()


def _logical_records(text: str) -> list[str]:
    records = []
    pending = ""
    for line in text.splitlines():
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        pending += " " + (line[:-1] if continued else line)
        if not continued:
            records.append(pending.strip())
            pending = ""
    if pending:
        raise ValueError("Unterminated requirement continuation")
    return records


def _requirements(text: str, *, locked: bool = False) -> list[Requirement]:
    requirements = []
    for record in _logical_records(text):
        parts = re.split(r"\s+--hash=", record)
        req = Requirement(parts[0])  # Invalid/unsupported requirement syntax must fail, never disappear.
        if req.url:
            raise ValueError(f"URL requirements are unsupported by the version lock contract: {req}")
        if locked:
            specs = list(req.specifier)
            if len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
                raise ValueError(f"Lock record must have one exact version: {req}")
            if len(parts) == 1 or any(not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", h.strip()) for h in parts[1:]):
                raise ValueError(f"Lock record needs its own valid sha256 hash: {req}")
        elif len(parts) != 1:
            raise ValueError(f"Hashes belong in requirements.lock: {req}")
        requirements.append(req)
    return requirements


def _target_environments() -> list[dict[str, str]]:
    # Explicit Python 3.12 reference targets, independent of the test host. Include the extra platforms
    # distinguished by the current universal lock. New marker dimensions require deliberate coverage below.
    platforms = [
        ("linux", "posix", "Linux"),
        ("darwin", "posix", "Darwin"),
        ("win32", "nt", "Windows"),
        ("cygwin", "posix", "CYGWIN_NT"),
        ("emscripten", "posix", "Emscripten"),
    ]
    return [
        {
            "python_version": "3.12",
            "sys_platform": platform,
            "os_name": os_name,
            "platform_system": system,
            "implementation_name": implementation.lower(),
            "platform_python_implementation": implementation,
        }
        for platform, os_name, system in platforms
        for implementation in ("CPython", "PyPy")
    ]


def _check_marker_coverage(req: Requirement, environment: dict[str, str]) -> None:
    if req.marker:
        unquoted = re.sub(r"\"[^\"]*\"|'[^']*'", "", str(req.marker))
        variables = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", unquoted)) - {"and", "or", "in", "not"}
        unsupported = variables - environment.keys()
        if unsupported:
            raise ValueError(f"Unsupported marker dimensions {sorted(unsupported)} in {req}; extend target coverage")


def _validate_lock(declarations: str, lock: str) -> None:
    direct = _requirements(declarations)
    pins = _requirements(lock, locked=True)
    if not direct or not pins:
        raise ValueError("Declarations and lock must not be empty")
    environments = _target_environments()
    for req in direct + pins:
        _check_marker_coverage(req, environments[0])
    errors = set()
    for environment in environments:
        target = f"{environment['sys_platform']}/{environment['implementation_name']}/3.12"
        versions: dict[str, set[Version]] = {}
        for pin in pins:
            if not pin.marker or pin.marker.evaluate(environment):
                versions.setdefault(canonicalize_name(pin.name), set()).add(Version(next(iter(pin.specifier)).version))
        for name, applicable in versions.items():
            if len(applicable) > 1:
                errors.add(f"{target}: overlapping versions for {name}: {sorted(map(str, applicable))}")
        for req in direct:
            if req.marker and not req.marker.evaluate(environment):
                continue
            eligible = [
                pin
                for pin in pins
                if canonicalize_name(pin.name) == canonicalize_name(req.name)
                and (not pin.marker or pin.marker.evaluate(environment))
            ]
            if not eligible:
                errors.add(f"{target}: missing compatible pin for {req}")
            for pin in eligible:
                version = next(iter(pin.specifier)).version
                if not req.specifier.contains(version):
                    errors.add(f"{target}: {pin.name}=={version} does not satisfy {req}")
    if errors:
        raise ValueError("\n".join(sorted(errors)) + "\nRun scripts/update_lock.sh")


def test_every_declared_requirement_is_pinned_with_hashes_in_the_lock():
    _validate_lock((ROOT / "requirements.txt").read_text(), (ROOT / "requirements.lock").read_text())


class TestLockContract(unittest.TestCase):
    """Synthetic offline regressions; also runnable with unittest without importing the app's conftest."""

    @staticmethod
    def pin(requirement: str) -> str:
        return requirement + " \\\n    --hash=sha256:" + "a" * 64 + "\n"

    def test_current_floor_gaps_and_upper_bound_are_rejected(self):
        for declaration, version in [
            ("SQLAlchemy>=2.1.3,<3", "2.1.2"),
            ("pydantic-settings>=2.16.0,<3", "2.15.0"),
            ("tzdata>=2026.5,<2027", "2026.4"),
            ("alpha>=1,<2", "2.0"),
        ]:
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, "does not satisfy"):
                _validate_lock(declaration, self.pin(f"{Requirement(declaration).name}=={version}"))

    def test_missing_direct_pin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing compatible pin for beta"):
            _validate_lock("alpha>=1\nbeta>=1", self.pin("alpha==1"))

    def test_prereleases_follow_the_declared_policy(self):
        with self.assertRaisesRegex(ValueError, "does not satisfy"):
            _validate_lock("alpha>=1.5rc1,<2", self.pin("alpha==1.4rc1"))
        _validate_lock("alpha>=1.5rc1,<2", self.pin("alpha==1.5rc1"))

    def test_distinct_overlapping_versions_are_rejected(self):
        for lock in [
            self.pin("alpha==1") + self.pin("alpha==1.5"),
            self.pin("alpha==1") + self.pin('alpha==1.5; sys_platform == "darwin"'),
            self.pin("alpha==1") + self.pin("beta==1") + self.pin("beta==1.5"),
        ]:
            with self.subTest(lock=lock), self.assertRaisesRegex(ValueError, "overlapping versions"):
                _validate_lock("alpha>=1,<2", lock)

    def test_each_pin_needs_its_own_hash_even_with_enough_global_hashes(self):
        lock = self.pin("alpha==1").rstrip() + " \\\n    --hash=sha256:" + "b" * 64 + "\nbeta==1\n"
        with self.assertRaisesRegex(ValueError, "own valid sha256 hash: beta"):
            _validate_lock("alpha>=1\nbeta>=1", lock)

    def test_unrelated_transitive_pin_also_needs_a_hash(self):
        with self.assertRaisesRegex(ValueError, "own valid sha256 hash: beta"):
            _validate_lock("alpha>=1", self.pin("alpha==1") + "beta==1")

    def test_canonical_names_extras_comments_and_continuations(self):
        _validate_lock(
            "Some_Package[feature]>=1, \\\n    <2  # direct extra\n",
            "# generated\n" + self.pin("some.package==1.5") + "    # via direct\n",
        )

    def test_platform_specific_pins_and_python_marker(self):
        _validate_lock(
            'alpha>=1; python_version == "3.12"',
            self.pin('alpha==1; sys_platform == "win32"') + self.pin('alpha==1.5; sys_platform != "win32"'),
        )
        _validate_lock('alpha>=1\nbeta>=1; python_version < "3.12"', self.pin("alpha==1"))

    def test_missing_platform_pin_and_any_incompatible_eligible_pin_are_rejected(self):
        cases = [
            self.pin('alpha==1; sys_platform != "win32"'),
            self.pin("alpha==1") + self.pin('alpha==0.5; sys_platform == "darwin"'),
            self.pin('alpha==1; platform_python_implementation != "PyPy"'),
        ]
        for lock in cases:
            with self.subTest(lock=lock), self.assertRaises(ValueError):
                _validate_lock("alpha>=1", lock)

    def test_unsupported_or_malformed_records_never_disappear(self):
        for declaration, lock in [
            ("-r other.txt", self.pin("alpha==1")),
            ('alpha>=1; platform_machine == "x86_64"', self.pin("alpha==1")),
            ('alpha>=1; python_full_version >= "3.12.1"', self.pin("alpha==1")),
            ('alpha>=1; extra == "feature"', self.pin("alpha==1")),
            ("alpha @ https://example.invalid/alpha.whl", self.pin("alpha==1")),
            ("alpha>=1", self.pin("alpha>=1")),
            ("alpha>=1", self.pin("alpha==1.*")),
            ("alpha>=1", "alpha==1 --hash=sha256:bad"),
            ("alpha>=1", self.pin("alpha==1") + "-r other.txt"),
            ("alpha>=1", "alpha==1 \\"),
        ]:
            with self.subTest(declaration=declaration, lock=lock), self.assertRaises(ValueError):
                _validate_lock(declaration, lock)


def test_the_image_installs_from_the_lock_with_hash_checking_and_never_seeds_demo_data():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "pip install --require-hashes --no-deps -r requirements.lock" in dockerfile
    assert "ENV SEED_DEMO_DATA=false" in dockerfile
