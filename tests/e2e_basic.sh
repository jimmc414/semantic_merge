#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

npm --prefix "$PROJECT_ROOT/workers/ts" install >/dev/null
npm --prefix "$PROJECT_ROOT/workers/ts" run build >/dev/null
python -m pip install -e "$PROJECT_ROOT" >/dev/null

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$TMP_DIR"
git init -q
git checkout -b main >/dev/null 2>&1 || git checkout main >/dev/null 2>&1

cat > a.ts <<'TS'
export function f(x: number){ return x+1; }
TS
git add a.ts
git commit -qm "base"

git checkout -qb branchA
sed -i 's/function f/function g/' a.ts
git commit -am "rename f->g" -q

git checkout -q main
git checkout -qb branchB
mkdir -p lib
git mv a.ts lib/a.ts
git commit -am "move a.ts to lib" -q

git checkout -q main
git config merge.semerge.driver "python3 $PROJECT_ROOT/scripts/semmerge-driver.py %O %A %B"
cat > .gitattributes <<'ATTR'
*.ts merge=semmerge
ATTR
git add .gitattributes
git commit -qm "enable semmerge driver"

git merge branchB -m "merge branchB" -q || true
git merge branchA -m "merge branchA" || true

if [[ ! -f lib/a.ts ]]; then
  echo "Expected lib/a.ts after merge" >&2
  exit 1
fi

if ! grep -q "function g" lib/a.ts; then
  echo "Merged file does not contain renamed function" >&2
  exit 1
fi

echo "Merge succeeded"
