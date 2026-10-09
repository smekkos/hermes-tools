#!/usr/bin/env bash
# Verify every line of tools.txt for real: download the archive, check its
# sha256, extract only the member, and require `--version` to name the pinned
# version (plus the `require` string unless "-"). Same checks the installer on
# hermes-prod runs; doing them in CI means a bad pin never reaches main.
#
#   bash scripts/verify.sh [tools.txt]      # exit 0 = all good
set -uo pipefail
MANIFEST=${1:-tools.txt}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
rc=0 n=0
while read -r name ver policy repo url member sha require extra; do
  case "$name" in ''|'#'*) continue ;; esac
  n=$((n+1))
  if [ -z "${require:-}" ] || [ -n "${extra:-}" ]; then echo "FAIL $name: malformed line (want 8 fields)"; rc=1; continue; fi
  case "$policy" in none|patch|minor|major) ;; *) echo "FAIL $name: unknown policy '$policy'"; rc=1; continue ;; esac
  case "$url" in https://*) ;; *) echo "FAIL $name: url must be https"; rc=1; continue ;; esac
  url=${url//\{version\}/$ver}; member=${member//\{version\}/$ver}
  d="$T/$name"; mkdir -p "$d/x"
  if ! curl -fsSL --max-time 300 -o "$d/a" "$url"; then echo "FAIL $name $ver: download failed: $url"; rc=1; continue; fi
  got=$(sha256sum "$d/a" | cut -d' ' -f1)
  [ "$got" = "$sha" ] || { echo "FAIL $name $ver: sha256 $got != pinned $sha"; rc=1; continue; }
  tar -xzf "$d/a" -C "$d/x" "./$member" 2>/dev/null || tar -xzf "$d/a" -C "$d/x" "$member" 2>/dev/null \
    || { echo "FAIL $name $ver: member $member not in archive"; rc=1; continue; }
  out=$(timeout 20 "$d/x/$member" --version 2>&1 | head -1)
  printf '%s' "$out" | grep -qF -- "$ver" || { echo "FAIL $name $ver: --version said '$out'"; rc=1; continue; }
  if [ "$require" != "-" ] && ! printf '%s' "$out" | grep -qF -- "$require"; then
    echo "FAIL $name $ver: --version lacks '$require': '$out'"; rc=1; continue
  fi
  echo "ok   $name $ver ($out)"
done <"$MANIFEST"
[ "$n" -gt 0 ] || { echo "FAIL: no tools in $MANIFEST"; rc=1; }
exit $rc
