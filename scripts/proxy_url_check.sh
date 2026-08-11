#!/bin/bash
# ============================================================================
# ProxyHub — URL reachability test via proxy
# ============================================================================
#
# Starts a proxy binary, waits for it to listen, curls a test URL through
# its SOCKS5 port, then tears everything down.  Pure bash — no Python.
#
# Usage:
#   ./test.sh <config> <type> <bin> <port> <url> <timeout> [tag]
#
#   config    absolute path to proxy config JSON
#   type      proxy type: xray | sslocal | sing-box
#   bin       absolute path to proxy binary
#   port      SOCKS5 port the proxy will listen on
#   url       test URL to curl through the proxy
#   timeout   curl --max-time (seconds)
#   tag       optional label for process cleanup (default: unknown)
#
# Flow:
#   1. Validate inputs — config exists, binary exists & is executable
#   2. Resolve run command per proxy type
#   3. Start proxy in its own process group (setsid) → write pidfile
#   4. wait_port — poll /dev/tcp until proxy accepts connections (max 15 s)
#   5. curl the test URL via SOCKS5, with smart retry on fast HTTP 000
#      (proxy may accept SOCKS5 handshake before outbound link is ready)
#   6. cleanup — three-layer kill: PGID → pgrep by tag → pgrep by config name
#   7. Output one JSON line, exit 0/1/2
#
# Output:
#   {"latency_ms":<ms>,"http_code":"<code>","error":"HTTP <code>"}
#   - On success, http_code is "204" and exit code is 0.
#   - On upstream failure, http_code is not "204" and exit code is 1.
#
# Exit codes:
#   0   HTTP 204 — proxy working, upstream reachable
#   1   proxy started but upstream test failed (HTTP != 204)
#   2   internal error — binary/config missing, proxy didn't start, etc.
# ============================================================================
set -euo pipefail

# ---- config ----

PORT_WAIT_MAX=15      # max seconds to wait for proxy to listen
CURL_RETRY_MAX=3      # max curl attempts
CURL_RETRY_DELAY=1    # seconds between retries

# ---- helpers ----

die() {
    local msg="$1"
    msg="${msg//\\/\\\\}"; msg="${msg//\"/\\\"}"
    printf '{"latency_ms":-1,"http_code":"0","error":"%s"}\n' "$msg"
    exit 2
}

cmd_for() {
    case "$1" in
        xray)     printf '%s run -config %s'  "$2" "$3" ;;
        sslocal)  printf '%s -c %s'           "$2" "$3" ;;
        sing-box) printf '%s run -c %s'       "$2" "$3" ;;
        *)        die "unknown bin_type: $1"  ;;
    esac
}

# ---- port wait (bash /dev/tcp, no deps) ----

wait_port() {
    local port="$1" i=0
    while [ $i -lt $((PORT_WAIT_MAX * 2)) ]; do
        timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/$port" 2>/dev/null && return 0
        sleep 0.5; i=$((i + 1))
    done
    return 1
}

# ---- cleanup (pgid → tag → config filename) ----

cleanup() {
    local pid_file="$1" tag="${2:-}" config="${3:-}" pid pgid hits name

    if [ -s "$pid_file" ]; then
        pid=$(head -n1 "$pid_file") || pid=
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ') || pgid=
            [ -n "$pgid" ] && { kill -TERM -- -"$pgid" 2>/dev/null || true; sleep 0.3; kill -KILL -- -"$pgid" 2>/dev/null || true; }
            kill -KILL "$pid" 2>/dev/null || true
        fi
    fi

    [ -n "$tag" ] && hits=$(pgrep -af "$tag" 2>/dev/null | grep -v 'proxy_url_check\.sh' | awk '{print $1}' || true)
    [ -n "${hits:-}" ] && echo "$hits" | xargs kill -KILL 2>/dev/null || true

    name=$(basename "${config:-}" 2>/dev/null) || name=
    [ -n "$name" ] && hits=$(pgrep -af "$name" 2>/dev/null | grep -v 'proxy_url_check\.sh' | awk '{print $1}' || true)
    [ -n "${hits:-}" ] && echo "$hits" | xargs kill -KILL 2>/dev/null || true

    rm -f "$pid_file"
}

# ---- main ----

CONFIG="$1"; TYPE="$2"; BIN="$3"; PORT="$4"; URL="$5"; TIMEOUT="$6"; TAG="${7:-unknown}"

# validate
[ -f "$CONFIG" ] || die "config not found: $CONFIG"
[ -f "$BIN" ]     || die "binary not found: $BIN"
[ -x "$BIN" ]     || chmod +x "$BIN" 2>/dev/null || true

PIDFILE="${CONFIG}.pid"
RUN_CMD=$(cmd_for "$TYPE" "$BIN" "$CONFIG")

# start proxy
BIN_DIR=$(dirname "$BIN")
PATH="$BIN_DIR:$PATH" setsid $RUN_CMD >/dev/null 2>&1 &
echo $! > "$PIDFILE"

wait_port "$PORT" || { cleanup "$PIDFILE" "$TAG" "$CONFIG"; die "proxy did not start on port $PORT"; }

# curl with smart retry
ATTEMPT=1; HTTP=000
T0=$(date +%s%N)

while [ $ATTEMPT -le $CURL_RETRY_MAX ]; do
    HTTP=$(curl -o /dev/null -s -w "%{http_code}" --max-time "$TIMEOUT" \
        --socks5-hostname "127.0.0.1:$PORT" "$URL" 2>/dev/null || echo "000")
    [ "$HTTP" = "204" ] && break

    NOW=$(date +%s%N); LAT=$(( (NOW - T0) / 1000000 ))
    if [ "$HTTP" = "000" ] && [ "$LAT" -lt 2000 ] && [ "$ATTEMPT" -lt "$CURL_RETRY_MAX" ]; then
        sleep "$CURL_RETRY_DELAY"
    else
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
done

T1=$(date +%s%N); LAT=$(( (T1 - T0) / 1000000 ))

cleanup "$PIDFILE" "$TAG" "$CONFIG"

printf '{"latency_ms":%d,"http_code":"%s","error":"HTTP %s"}\n' "$LAT" "$HTTP" "$HTTP"
[ "$HTTP" = "204" ] && exit 0 || exit 1
