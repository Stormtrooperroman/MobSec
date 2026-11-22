#!/bin/bash
set -e

REAL_QEMU="/opt/adt/tools/qemu/bin/qemu-system-x86_64.real"

if [[ ! -x "$REAL_QEMU" ]]; then
    echo "Original QEMU binary not found: $REAL_QEMU" >&2
    exit 1
fi

ARGS=()
SKIP_NEXT=0

for arg in "$@"; do
    if [[ "$SKIP_NEXT" == 1 ]]; then
        SKIP_NEXT=0
        continue
    fi

    if [[ "$arg" == "-display" ]]; then
        SKIP_NEXT=1
        continue
    fi

    ARGS+=("$arg")
done

exec "$REAL_QEMU" \
    "${ARGS[@]}" \
    -display none \
    -vnc 0.0.0.0:1,websocket=5701 \
    -qmp tcp:127.0.0.1:4444,server=on,wait=off
