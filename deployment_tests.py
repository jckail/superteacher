"""Smoke test a running deployment: python deployment_tests.py https://your-host"""
import sys

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
with httpx.Client(base_url=base, timeout=15) as c:
    health = c.get("/api/health").json()
    assert health["status"] == "healthy", health
    assert c.get("/api/overview").status_code == 200
    assert "<div id=\"root\">" in c.get("/").text, "frontend not served"
    print(f"OK  {base}  ai={'on' if health['ai'] else 'off'}")
