#!/usr/bin/env bash
# Render every ```mermaid block in README.md, docs/**/*.md and contracts/**/*.md to
# docs/rendered/<name>.svg and docs/rendered/<name>.png (scale 2, slide-ready).
# <name> comes from a first-line comment inside the block:   %% name: dfd-level-0
# otherwise it falls back to <path_with_underscores>-<n>.
# Fails if any block does not parse. Requires mmdc (@mermaid-js/mermaid-cli).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/rendered"
MMDC="${MMDC:-mmdc}"
SCALE="${PNG_SCALE:-2}"
FORMATS="${FORMATS:-svg png}"
rm -rf "$OUT"; mkdir -p "$OUT"
PCFG="$(mktemp)"
if [[ -n "${CHROME_PATH:-}" ]]; then
  echo "{\"executablePath\":\"$CHROME_PATH\",\"args\":[\"--no-sandbox\"]}" > "$PCFG"
else
  echo '{"args":["--no-sandbox"]}' > "$PCFG"
fi
while IFS= read -r md; do
  rel="${md#$ROOT/}"; base="$(echo "${rel%.md}" | tr '/' '_')"
  awk -v out="$OUT" -v base="$base" '
    /^```mermaid[[:space:]]*$/ {n++; inb=1; first=1; buf=""; name=sprintf("%s-%d", base, n); next}
    inb && /^```[[:space:]]*$/ {
      inb=0; f=out "/" name ".mmd";
      if (seen[name]++) { print "duplicate diagram name: " name > "/dev/stderr"; exit 3 }
      printf "%s", buf > f; close(f); next }
    inb { if (first && match($0, /^[[:space:]]*%%[[:space:]]*name:[[:space:]]*[A-Za-z0-9._-]+/)) {
            s=$0; sub(/^[[:space:]]*%%[[:space:]]*name:[[:space:]]*/, "", s); sub(/[[:space:]].*$/, "", s); name=s }
          first=0; buf = buf $0 "\n" }' "$md"
done < <(find "$ROOT/README.md" "$ROOT/docs" "$ROOT/contracts" -name '*.md' -not -path '*/rendered/*' | sort)
fail=0; count=0
for mmd in "$OUT"/*.mmd; do
  [[ -e "$mmd" ]] || continue
  count=$((count+1)); stem="${mmd%.mmd}"; okall=1
  for fmt in $FORMATS; do
    extra=(); [[ "$fmt" == png ]] && extra=(-s "$SCALE")
    if ! "$MMDC" -q -p "$PCFG" -i "$mmd" -o "$stem.$fmt" -b white "${extra[@]}" >/dev/null 2>"$mmd.err"; then
      echo "  FAIL ${mmd#$ROOT/} ($fmt): $(head -c 400 "$mmd.err")"; okall=0; break
    fi
  done
  if [[ $okall == 1 ]]; then echo "  OK   ${stem#$ROOT/}.{${FORMATS// /,}}"; rm -f "$mmd.err"; else fail=$((fail+1)); fi
done
rm -f "$PCFG" "$OUT"/*.mmd "$OUT"/*.err
echo "$count diagrams, $fail failed"
exit $fail
