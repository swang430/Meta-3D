#!/bin/bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
FAKE_BIN=$(mktemp -d)
trap 'rm -rf "$FAKE_BIN"' EXIT

cat >"$FAKE_BIN/ps" <<'EOF'
#!/bin/bash
case "$2" in
    101) printf '%s\n' '/usr/local/bin/python3.12' ;;
    102) printf '%s\n' 'node' ;;
    103) printf '%s\n' '/workspace/node_modules/.bin/vite' ;;
    104) printf '%s\n' 'uvicorn' ;;
    105) printf '%s\n' '/usr/local/bin/python3.12' ;;
    106) printf '%s\n' 'node' ;;
    201) printf '%s\n' '/Applications/Docker.app/Contents/MacOS/com.docker.backend' ;;
    202) printf '%s\n' 'ssh' ;;
    203) printf '%s\n' 'unknown-helper' ;;
    *) exit 1 ;;
esac
EOF
chmod +x "$FAKE_BIN/ps"
cat >"$FAKE_BIN/lsof" <<'EOF'
#!/bin/bash
if [ "$1" = "-a" ]; then
    case "$3" in
        101|102|103|104) printf 'n%s\n' "$FAKE_REPO_ROOT/api-service" ;;
        105|106) printf '%s\n' 'n/tmp/another-project' ;;
        *) exit 1 ;;
    esac
    exit 0
fi
printf '%s\n' '201'
EOF
cat >"$FAKE_BIN/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$FAKE_BIN/lsof" "$FAKE_BIN/sleep"
export FAKE_REPO_ROOT="$REPO_ROOT"
PATH="$FAKE_BIN:$PATH"

# shellcheck source=../lib/port-guard.sh
source "$REPO_ROOT/scripts/lib/port-guard.sh"

for pid in 101 102 103 104; do
    if ! is_project_dev_pid "$pid"; then
        echo "expected project dev PID $pid to be allowlisted" >&2
        exit 1
    fi
done

for pid in 105 106 201 202 203 '' invalid; do
    if is_project_dev_pid "$pid"; then
        echo "expected unknown/non-project PID '$pid' to be protected" >&2
        exit 1
    fi
done

set +e
cleanup_output=$(PATH="$PATH" bash "$REPO_ROOT/scripts/cleanup-ports.sh" 2>&1)
cleanup_status=$?
set -e
if [ "$cleanup_status" -eq 0 ]; then
    echo "expected cleanup to fail closed while protected PIDs still hold ports" >&2
    echo "$cleanup_output" >&2
    exit 1
fi
if printf '%s' "$cleanup_output" | grep -q '正在终止'; then
    echo "protected PID reached the termination branch" >&2
    exit 1
fi

set +e
safe_start_output=$(PATH="$PATH" bash "$REPO_ROOT/scripts/safe-start.sh" 2>&1 </dev/null)
safe_start_status=$?
set -e
if [ "$safe_start_status" -eq 0 ]; then
    echo "expected safe-start to fail closed while protected PIDs still hold ports" >&2
    exit 1
fi
if printf '%s' "$safe_start_output" | grep -q '端口检查完成'; then
    echo "safe-start advanced past a protected port holder" >&2
    exit 1
fi

for operational_doc in \
    "$REPO_ROOT/scripts/README.md" \
    "$REPO_ROOT/docs/guides/quickstart.md"; do
    if grep -Eq 'lsof.*\|.*xargs.*kill|sudo.*kill.*-9' "$operational_doc"; then
        echo "operational documentation bypasses the shared port guard: $operational_doc" >&2
        exit 1
    fi
done

echo "port guard allowlist tests passed"
