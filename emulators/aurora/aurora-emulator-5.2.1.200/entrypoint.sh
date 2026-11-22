#!/bin/bash
set -e

EMU_STARTED=0
export PATH="/opt/adt/bin:$PATH"

cleanup() {
    echo "Stopping emulator..."

    /opt/adt/bin/adt emulator stop || echo "Failed to stop emulator" >&2

    echo "Emulator stopped"
}

# Adds the public key to the guest's authorized_keys for the specified user.
# The guest reads /etc/ssh/authorized_keys/%u/authorized_keys from the shared folder,
# which on the host is located at $EMU_DIR/ssh/<user>/.
authorize_key() {
    local user="$1" pub="$2"
    local dir="$EMU_DIR/ssh/$user"
    local file="$dir/authorized_keys"

    mkdir -p "$dir"
    touch "$file"
    if ! grep -qxF "$(cat "$pub")" "$file"; then
        # leading newline in case the file didn't end with \n
        printf '\n%s\n' "$(cat "$pub")" >> "$file"
        echo "Key added for user $user"
    else
        echo "Key for user $user already exists"
    fi
}

trap cleanup EXIT
trap 'exit 0' SIGTERM SIGINT

RELEASE="5.2.1.200"
EMU_DIR="/opt/adt/emulators/${RELEASE}/DefaultEmulator"
STATE="/opt/adt/emulators/.adt-state"
SSH_USER="${SSH_USER:-defaultuser}"
NOVNC_PORT="${NOVNC_PORT:-6080}"

QEMU_BIN="/opt/adt/tools/qemu/bin"

if [[ ! -x "$QEMU_BIN/qemu-system-x86_64" ]]; then
    echo "QEMU wrapper not found or not executable" >&2
    exit 1
fi

if [[ ! -x "$QEMU_BIN/qemu-system-x86_64.real" ]]; then
    echo "Original QEMU binary not found" >&2
    exit 1
fi

mkdir -p "$STATE" /opt/adt/ssh
mkdir -p /root/.ssh
chmod 700 /root/.ssh

if [[ -f "$STATE/id_rsa" ]]; then
    cp -a "$STATE/id_rsa" "$STATE/id_rsa.pub" /opt/adt/ssh/
fi

for f in emulators.toml devices.toml; do
    if [[ -f "$STATE/$f" ]]; then
        cp -a "$STATE/$f" "/opt/adt/$f"
    fi
done

if [[ ! -d "$EMU_DIR" ]]; then
    echo "Emulator directory not found at $EMU_DIR" >&2
    echo "Mount the emulators folder to /opt/adt/emulators" >&2
    # Don't exit - allow override with commands
fi

# If commands are provided, execute them (e.g. sleep infinity for dev)
if [[ $# -gt 0 ]]; then
    exec "$@"
fi

if ! grep -qs "emulator-${RELEASE}" /opt/adt/emulators.toml 2>/dev/null; then
    echo "Registering emulator-${RELEASE}..."

    /opt/adt/bin/adt emulator add "emulator-${RELEASE}" "$EMU_DIR" \
        || echo "Registration failed" >&2
fi

for f in \
    /opt/adt/ssh/id_rsa \
    /opt/adt/ssh/id_rsa.pub \
    /opt/adt/emulators.toml \
    /opt/adt/devices.toml
do
    if [[ -f "$f" ]]; then
        cp -a "$f" "$STATE/"
    fi
done

if [[ ! -f /opt/adt/ssh/id_rsa || ! -f /opt/adt/ssh/id_rsa.pub ]]; then
    echo "Generating SSH key..."
    rm -f /opt/adt/ssh/id_rsa /opt/adt/ssh/id_rsa.pub
    ssh-keygen -t rsa -b 4096 -N "" -f /opt/adt/ssh/id_rsa -C "adt-docker" >/dev/null
    cp -a /opt/adt/ssh/id_rsa /opt/adt/ssh/id_rsa.pub "$STATE/"
fi
chmod 600 /opt/adt/ssh/id_rsa

if [[ -d "$EMU_DIR" ]]; then
    authorize_key "$SSH_USER" /opt/adt/ssh/id_rsa.pub
    authorize_key root        /opt/adt/ssh/id_rsa.pub
else
    echo "No $EMU_DIR, keys not added" >&2
fi

cat > /root/.ssh/config <<EOF
Host emu
    HostName localhost
    Port 2223
    User ${SSH_USER}
    IdentityFile /opt/adt/ssh/id_rsa
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR

Host emu-root
    HostName localhost
    Port 2223
    User root
    IdentityFile /opt/adt/ssh/id_rsa
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOF

chmod 600 /root/.ssh/config

echo "======================================"
echo " Aurora OS Emulator environment ready"
echo "======================================"
echo "VNC:       5901"
echo "WebSocket: 5701"
echo "QMP:       127.0.0.1:4444"
echo "SSH:       localhost:2223  (ssh emu / ssh emu-root)"
echo "======================================"

/opt/adt/bin/adt emulator config set point_mode mouse
/opt/adt/bin/adt emulator config set downscale 1

echo "Checking and clearing stale state..."
# Kill any leftover qemu processes from previous runs
pkill -f qemu-system-x86_64 || true
sleep 1

# Mark all emulators as stopped to reset state
/opt/adt/bin/adt emulator list 2>/dev/null | grep -o 'emulator-[^ ]*' | while read emu; do
    echo "Resetting state for $emu..."
    /opt/adt/bin/adt emulator stop "$emu" 2>/dev/null || true
done

echo "Starting emulator..."

# Start with retry logic for connection issues
MAX_RETRIES=3
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    /opt/adt/bin/adt emulator start --headless
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Emulator started successfully"
        break
    else
        echo "Start attempt failed (exit code: $EXIT_CODE), retrying..."
        RETRY=$((RETRY + 1))
        if [ $RETRY -lt $MAX_RETRIES ]; then
            sleep 2
        fi
    fi
done

if [ $EXIT_CODE -ne 0 ]; then
    echo "adt command failed with error: $EXIT_CODE"
    exit 1
fi

while true; do
    sleep 3600
done
