#!/usr/bin/env bash
set -euo pipefail

deployment_root="${1:?Provide the independent deployment directory}"
app_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
runtime_root="$deployment_root/runtime"
if [[ ! -f "$runtime_root/service.env" ]]; then
    printf 'Missing runtime/service.env\n' >&2
    exit 1
fi
set -a
source "$runtime_root/service.env"
set +a
port="${CLUB_PORT:-6006}"
mkdir -p "$runtime_root/logs"
if [[ -f "$runtime_root/gunicorn.pid" ]]; then
    existing_pid="$(cat "$runtime_root/gunicorn.pid")"
    if [[ "$existing_pid" =~ ^[0-9]+$ ]] && kill -0 "$existing_pid" 2>/dev/null; then
        printf 'An existing process has PID %s; stop the owned test service before restarting.\n' "$existing_pid" >&2
        exit 1
    fi
fi
"$deployment_root/venv/bin/python" - "$port" <<'PY'
import socket
import sys
with socket.socket() as listener:
    listener.bind(('0.0.0.0', int(sys.argv[1])))
PY
"$deployment_root/venv/bin/gunicorn" \
    --chdir "$app_root" --pythonpath "$app_root/src" \
    --bind "0.0.0.0:$port" --workers 1 --worker-class gthread --threads 4 \
    --timeout 60 --graceful-timeout 15 --max-requests 1000 --max-requests-jitter 100 \
    --pid "$runtime_root/gunicorn.pid" --daemon \
    --access-logfile "$runtime_root/logs/access.log" \
    --access-logformat '%(h)s %(t)s "%(m)s %(U)s" %(s)s %(L)s' \
    --error-logfile "$runtime_root/logs/error.log" \
    'campus_clubs.cloud_test:create_cloud_test_app()'
"$deployment_root/venv/bin/python" - "$port" <<'PY'
import sys
import time
import urllib.error
import urllib.request
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(30):
    try:
        client.open(f'http://127.0.0.1:{sys.argv[1]}/', timeout=2).close()
    except urllib.error.HTTPError as error:
        if error.code == 401 and 'Campus club test' in error.headers.get('WWW-Authenticate', ''):
            print('Authenticated test service is ready on port', sys.argv[1])
            break
        raise
    except urllib.error.URLError:
        time.sleep(.3)
    else:
        raise SystemExit('Unexpected unprotected response; check the listener.')
else:
    raise SystemExit('Service did not become ready; inspect runtime/logs/error.log.')
PY
