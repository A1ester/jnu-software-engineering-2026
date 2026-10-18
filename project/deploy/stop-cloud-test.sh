#!/usr/bin/env bash
set -euo pipefail
deployment_root="${1:?Provide the independent deployment directory}"
app_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
"$deployment_root/venv/bin/python" - "$deployment_root/runtime/gunicorn.pid" "$app_root" <<'PY'
import os
from pathlib import Path
import signal
import sys
import time
pid_file, expected_cwd = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
if not pid_file.is_file():
    raise SystemExit('No test-service PID file exists.')
pid = int(pid_file.read_text().strip())
process = Path('/proc') / str(pid)
if not process.exists():
    raise SystemExit('The recorded test process is already stopped.')
command = (process / 'cmdline').read_bytes()
if (process / 'cwd').resolve() != expected_cwd or b'gunicorn' not in command:
    raise SystemExit('PID ownership check failed; no process was stopped.')
os.kill(pid, signal.SIGTERM)
for attempt in range(60):
    if not process.exists() or not pid_file.exists():
        print('Test service stopped:', pid)
        break
    time.sleep(.3)
else:
    raise SystemExit('Graceful stop is still pending; inspect the test-service logs.')
PY
