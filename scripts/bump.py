#!/usr/bin/env python3
"""Bump tools.txt to the newest release each tool's policy allows.

Run weekly by .github/workflows/bump.yml, followed by scripts/verify.sh, which
downloads every pinned archive, checks its sha256 and runs `--version`. Only if
that passes is the change committed to main, and hermes-prod installs it within
15 minutes (its installer runs the same checks again before switching).

Policy per tool (column 3): none | patch | minor | major, measured against the
version currently pinned. The sha256 written is computed here from the actual
download, never taken from release notes or checksum files.

    python3 scripts/bump.py [tools.txt]      # rewrites in place, prints changes
Exit 0 always unless the manifest cannot be read; a tool that fails to bump is
reported and left as it was.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Optional

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
POLICIES = ("none", "patch", "minor", "major")


def parse_version(tag: str) -> Optional[tuple[int, int, int]]:
    m = _VERSION.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def pick(current: str, releases: Iterable[dict], policy: str) -> Optional[str]:
    """Newest release allowed by policy that is newer than current, else None."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    cur = parse_version(current)
    if policy == "none" or cur is None:
        return None
    best = None
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        v = parse_version(r.get("tag_name", ""))
        if v is None or v <= cur:
            continue
        if policy == "patch" and v[:2] != cur[:2]:
            continue
        if policy == "minor" and v[0] != cur[0]:
            continue
        if best is None or v > best:
            best = v
    return ".".join(map(str, best)) if best else None


def bump_manifest(text: str, releases: Callable[[str], list], fetch: Callable[[str], bytes]) -> tuple[str, list[str]]:
    out, report = [], []
    for line in text.splitlines(keepends=True):
        fields = line.split()
        if not fields or fields[0].startswith("#") or len(fields) != 8:
            out.append(line)
            continue
        name, ver, policy, repo, url = fields[:5]
        try:
            new = pick(ver, releases(repo), policy)
        except Exception as exc:  # API trouble for one tool must not stop the others
            report.append(f"{name} {ver}: release lookup FAILED: {exc}")
            out.append(line)
            continue
        if not new:
            out.append(line)
            continue
        try:
            sha = hashlib.sha256(fetch(url.replace("{version}", new))).hexdigest()
        except Exception as exc:
            report.append(f"{name} {ver} -> {new} FAILED: {exc}")
            out.append(line)
            continue
        # Replace exactly the version and sha256 tokens; keep spacing as it was.
        parts = re.split(r"(\s+)", line.rstrip("\n"))
        tokens = parts[0::2]
        tokens[1], tokens[6] = new, sha
        parts[0::2] = tokens
        out.append("".join(parts) + ("\n" if line.endswith("\n") else ""))
        report.append(f"{name} {ver} -> {new}")
    return "".join(out), report


def _github_releases(repo: str) -> list:
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases?per_page=50",
                                 headers={"Accept": "application/vnd.github+json"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as r:
        return r.read()


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "tools.txt")
    text = path.read_text()
    new, report = bump_manifest(text, _github_releases, _fetch)
    for line in report:
        print(line)
    if new != text:
        path.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
