"""Root pytest bootstrap: runs before tests/ is imported.

The shared fixtures build apps without credentials, so the suite runs with auth explicitly disabled.
Real auth behaviour is tested in tests/test_auth.py with an app created with ``settings=``.
"""

import os

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("DATABASE_URL", "sqlite://")
