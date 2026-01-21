#!/usr/bin/env bash
set -euo pipefail

cd /opt/manganegus

git pull --ff-only origin main

python3 - <<'PY'
from pathlib import Path
src = Path('requirements.txt').read_text().splitlines()
out = []
for line in src:
    stripped = line.strip()
    if stripped.startswith('rapidfuzz>=') or stripped.startswith('rapidfuzz=='):
        out.append('rapidfuzz==3.13.0')
    elif stripped.startswith('alembic>=') or stripped.startswith('alembic=='):
        out.append('alembic==1.16.5')
    else:
        out.append(line)
Path('requirements.pi.txt').write_text('\n'.join(out) + '\n')
PY

LOCK_FILE="/opt/manganegus/requirements.lock"
REQ_FILE="/opt/manganegus/requirements.pi.txt"

if [ -f "${LOCK_FILE}" ]; then
  /opt/manganegus/.venv/bin/pip install -r "${LOCK_FILE}"
else
  /opt/manganegus/.venv/bin/pip install -r "${REQ_FILE}"
fi

set -a
. /opt/manganegus/.env
set +a
/opt/manganegus/.venv/bin/alembic -c /opt/manganegus/alembic.ini upgrade head

sudo systemctl restart manganegus
