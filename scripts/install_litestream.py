"""Download a pinned Litestream release and install its binary, refusing anything that fails the checksum.

Usage: install_litestream.py VERSION SHA256 [DEST_DIR]   (linux/amd64 tarball; DEST_DIR defaults to /usr/local/bin)
Used by the Dockerfile so the build needs neither curl nor BuildKit-only features.
"""

import hashlib
import io
import os
import sys
import tarfile
import urllib.request

URL = "https://github.com/benbjohnson/litestream/releases/download/v{v}/litestream-{v}-linux-x86_64.tar.gz"


def install(version: str, sha256: str, dest: str, url: str | None = None) -> str:
    data = urllib.request.urlopen(url or URL.format(v=version), timeout=60).read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256.lower():
        raise SystemExit(f"checksum mismatch for litestream {version}: expected {sha256}, got {actual}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = next((m for m in tar.getmembers() if os.path.basename(m.name) == "litestream" and m.isfile()), None)
        if member is None:
            raise SystemExit("litestream binary not found in the archive")
        out = os.path.join(dest, "litestream")
        with tar.extractfile(member) as src, open(out, "wb") as f:
            f.write(src.read())
    os.chmod(out, 0o755)
    return out


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit(__doc__)
    print(f"installed {install(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else '/usr/local/bin')}")
