"""Spec for scripts/bump.py: the weekly auto-update of tools.txt.

Offline: GitHub's release list and the download are injected, so these tests
need no network. The real end-to-end check (download, sha256, --version) is
scripts/verify.sh, which CI runs on every push and after every bump.

    python3 -m unittest discover -s tests -v

  B1  versions parse from tags "v1.2.3" and "1.2.3"; anything else is ignored
  B2  policy decides how far a tool may move from its pinned version:
        none  -> never;  patch -> same major.minor;  minor -> same major;  major -> anything newer
  B3  drafts and prereleases are never picked; neither is anything older
  B4  a bump rewrites only version and sha256 of that one line; comments,
      other lines and column layout are kept byte-for-byte
  B5  the sha256 written is the sha256 of the archive at the url with the
      NEW version substituted (computed, not trusted from anywhere)
  B6  a failing download for one tool leaves that line untouched and the
      others still bump; the run reports the failure
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bump  # noqa: E402

GH = "gh 2.101.0 minor cli/cli https://github.com/cli/cli/releases/download/v{version}/gh_{version}_linux_amd64.tar.gz gh_{version}_linux_amd64/bin/gh " + "a" * 64 + " -"
HIM = "himalaya 2.1.0 patch pimalaya/himalaya https://github.com/pimalaya/himalaya/releases/download/v{version}/himalaya.x86_64-linux.tgz himalaya " + "b" * 64 + " +msgraph"


def rel(tag, draft=False, pre=False):
    return {"tag_name": tag, "draft": draft, "prerelease": pre}


class Versions(unittest.TestCase):
    def test_parse(self):  # B1
        self.assertEqual(bump.parse_version("v2.2.1"), (2, 2, 1))
        self.assertEqual(bump.parse_version("2.101.0"), (2, 101, 0))
        for bad in ("nightly", "v2.2", "v2.2.1-rc1", "release-2.2.1", ""):
            self.assertIsNone(bump.parse_version(bad), bad)

    def test_policy(self):  # B2 B3
        releases = [rel("v2.1.0"), rel("v2.1.3"), rel("v2.2.1"), rel("v3.0.0"), rel("v2.1.9", pre=True),
                    rel("v2.1.8", draft=True), rel("v2.0.9"), rel("nightly")]
        self.assertIsNone(bump.pick("2.1.0", releases, "none"))
        self.assertEqual(bump.pick("2.1.0", releases, "patch"), "2.1.3")
        self.assertEqual(bump.pick("2.1.0", releases, "minor"), "2.2.1")
        self.assertEqual(bump.pick("2.1.0", releases, "major"), "3.0.0")
        self.assertIsNone(bump.pick("2.2.1", [rel("v2.1.3"), rel("v2.2.1")], "minor"))

    def test_unknown_policy_is_an_error(self):
        with self.assertRaises(ValueError):
            bump.pick("1.0.0", [rel("v1.0.1")], "always")


class Rewrite(unittest.TestCase):
    def manifest(self):
        return "# name version policy repo url member sha256 require\n\n" + GH + "\n" + HIM + "\n"

    def test_bump_rewrites_only_that_line(self):  # B4 B5
        archive = b"fake gh 2.102.0 archive"
        seen = []

        def releases(repo):
            return {"cli/cli": [rel("v2.102.0"), rel("v2.101.0")],
                    "pimalaya/himalaya": [rel("v2.2.1"), rel("v2.1.0")]}[repo]

        def fetch(url):
            seen.append(url)
            return archive

        new, report = bump.bump_manifest(self.manifest(), releases, fetch)
        self.assertEqual(seen, ["https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_linux_amd64.tar.gz"])
        lines = new.splitlines()
        self.assertEqual(lines[0], "# name version policy repo url member sha256 require")
        self.assertEqual(lines[1], "")
        f = lines[2].split()
        self.assertEqual((f[0], f[1], f[6]), ("gh", "2.102.0", hashlib.sha256(archive).hexdigest()))
        self.assertEqual(f[4], "https://github.com/cli/cli/releases/download/v{version}/gh_{version}_linux_amd64.tar.gz")
        self.assertEqual(lines[3], HIM)            # patch policy: 2.2.1 not allowed
        self.assertEqual(report, ["gh 2.101.0 -> 2.102.0"])
        self.assertTrue(new.endswith("\n"))

    def test_nothing_to_do(self):
        new, report = bump.bump_manifest(self.manifest(), lambda r: [rel("v2.101.0"), rel("v2.1.0")], lambda u: b"")
        self.assertEqual((new, report), (self.manifest(), []))

    def test_uv_unprefixed_tags_and_member_path(self):  # B2 B5 with a 0.x tool whose tags have no "v"
        uv = ("uv 0.12.24 minor astral-sh/uv https://github.com/astral-sh/uv/releases/download/{version}/"
              "uv-x86_64-unknown-linux-musl.tar.gz uv-x86_64-unknown-linux-musl/uv " + "c" * 64 + " -")
        seen = []

        def fetch(url):
            seen.append(url)
            return b"uv archive"

        new, report = bump.bump_manifest(uv + "\\n", lambda r: [rel("0.13.1"), rel("0.12.24"), rel("1.0.0")], fetch)
        self.assertEqual(seen, ["https://github.com/astral-sh/uv/releases/download/0.13.1/uv-x86_64-unknown-linux-musl.tar.gz"])
        f = new.split()
        self.assertEqual((f[0], f[1], f[5]), ("uv", "0.13.1", "uv-x86_64-unknown-linux-musl/uv"))
        self.assertEqual(f[6], hashlib.sha256(b"uv archive").hexdigest())
        self.assertEqual(report, ["uv 0.12.24 -> 0.13.1"])  # minor policy never jumps to 1.0.0

    def test_failed_download_leaves_line(self):  # B6
        def releases(repo):
            return [rel("v2.102.0")] if repo == "cli/cli" else [rel("v2.1.4")]

        def fetch(url):
            if "cli/cli" in url:
                raise OSError("HTTP 404")
            return b"him"

        new, report = bump.bump_manifest(self.manifest(), releases, fetch)
        lines = new.splitlines()
        self.assertEqual(lines[2], GH)
        self.assertEqual(lines[3].split()[1], "2.1.4")
        self.assertIn("gh 2.101.0 -> 2.102.0 FAILED: HTTP 404", report)
        self.assertIn("himalaya 2.1.0 -> 2.1.4", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
