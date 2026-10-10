# hermes-tools

Pinned third-party CLI binaries for the hermes-prod droplet (`himalaya`, `gh`).
**This repo is a version list, not a place for binaries.** Each line in
[`tools.txt`](tools.txt) names an official release archive and its sha256.

## How it reaches production (no manual steps)

```text
Monday 05:17 UTC  bump.yml: newest release allowed by each tool's policy
                  → sha256 computed from the real download → verify.sh → commit to main
every 15 min      hermes-prod git-sync: /var/lib/hermes/data/hermes-tools = main
every 15 min      hermes-prod tools-install.sh (smekkos/hermes-do):
                  download → sha256 check → --version smoke test as the agent user
                  → switch cli-tools/current/<name> → links in /opt/data/bin and /opt/data/.local/bin
```

Inside the container a tool is available as plain `himalaya` / `gh`
(`/opt/data/.local/bin` is on `PATH`) and at `/opt/data/bin/<name>`.

Nothing in this repository is executed on the droplet. The installer lives in
`smekkos/hermes-do` (`deploy/tools-install.sh`). A push here can only choose
*which* archive is installed. It must match its sha256, and the binary only ever
runs as the container's runtime user.

## Policy (column 3)

| Policy | The weekly bump may move to |
|---|---|
| `none` | nothing; manual only |
| `patch` | `x.y.*` (himalaya: its 2.2 release changed features, so minor bumps are a deliberate step) |
| `minor` | `x.*.*` |
| `major` | anything newer |

## By hand

- **Upgrade/downgrade now:** edit `version` and `sha256`
  (`curl -sL <url> | sha256sum`), run `bash scripts/verify.sh`, push.
- **Roll back:** revert the bump commit. hermes-prod keeps the previous
  version on disk, so the switch back needs no download.
- **Add a tool:** one line. It must be a static Linux x86_64 build whose
  `--version` prints its version.
- **Bump right now:** Actions → bump → Run workflow.

## Tests

```bash
python3 -m unittest discover -s tests -v   # bump policy and manifest rewrite (offline)
bash scripts/verify.sh                     # every pin downloads, matches, runs
```

CI runs both on every push. The installer's own tests are
`deploy/test-tools-install.sh` in `smekkos/hermes-do`.
