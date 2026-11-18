#!/usr/bin/env bash
# Extract every ```mermaid block from docs/**/*.md and contracts/**/*.md, render to docs/rendered/<file>-<n>.svg.
# Fails if any block does not parse. Requires mmdc (@mermaid-js/mermaid-cli).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/rendered"
MMDC="${MMDC:-mmdc}"
mkdir -p "$OUT"
PCFG="$(mktemp)"
if [[ -n "${CHROME_PATH:-}" ]]; then
  echo "{\"executablePath\":\"$CHROME_PATH\",\"args\":[\"--no-sandbox\"]}" > "$PCFG"
else
  echo '{"args":["--no-sandbox"]}' > "$PCFG"
fi
fail=0; count=0
while IFS= read -r md; do
  rel="${md#$ROOT/}"; base="$(echo "${rel%.md}" | tr '/' '_')"
  awk -v out="$OUT/$base" '
    /^```mermaid[[:space:]]*$/ {n++; f=sprintf("%s-%d.mmd", out, n); inb=1; next}
    inb && /^```[[:space:]]*$/ {inb=0; close(f); next}
    inb {print > f}' "$md"
done < <(find "$ROOT/README.md" "$ROOT/docs" "$ROOT/contracts" -name '*.md' -not -path '*/rendered/*' | sort)
for mmd in "$OUT"/*.mmd; do
  [[ -e "$mmd" ]] || continue
  count=$((count+1))
  svg="${mmd%.mmd}.svg"
  if "$MMDC" -q -p "$PCFG" -i "$mmd" -o "$svg" -b white >/dev/null 2>"$mmd.err"; then
    echo "  OK   ${svg#$ROOT/}"; rm -f "$mmd.err"
  else
    echo "  FAIL ${mmd#$ROOT/}: $(head -c 400 "$mmd.err")"; fail=$((fail+1))
  fi
done
rm -f "$PCFG" "$OUT"/*.mmd
echo "$count diagrams, $fail failed"
exit $fail
