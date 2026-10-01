"""Smoke test a running deployment: python deployment_tests.py https://your-host

If the deployment has auth enabled, pass the passcode via the AUTH_PASSWORD environment variable.
"""

import os
import sys

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
password = os.environ.get("AUTH_PASSWORD")
H = {"X-Requested-With": "deployment_tests"}

with httpx.Client(base_url=base, timeout=15, headers=H) as c:
    health = c.get("/api/health").json()
    assert health["status"] == "healthy", health
    me = c.get("/api/auth/me")
    if me.status_code == 401:
        assert c.get("/api/overview").status_code == 401, "API is not gated while auth is on"
        assert password, "deployment requires auth: set AUTH_PASSWORD"
        r = c.post("/api/auth/login", json={"password": password})
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    assert c.get("/api/overview").status_code == 200
    assert '<div id="root">' in c.get("/").text, "frontend not served"
    print(f"OK  {base}  ai={'on' if health['ai'] else 'off'}  auth={'on' if me.status_code == 401 else 'off'}")
