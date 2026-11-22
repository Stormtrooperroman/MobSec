FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV AURORA_VERSION=5.2.1.200
ENV SDK_URL=https://sdk-repo.omprussia.ru/sdk/installers/5.2.1/5.2.1.200-release/AuroraEmulator/standalone-emulator-5.2.1.200-linux-x86_64.7z

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils diffutils gawk ca-certificates \
        openssh-client iproute2 curl p7zip-full \
        libgtk-3-0t64 \
        libsdl2-2.0-0 libasound2t64 libpulse0 \
        libx11-6 libxcomposite1 libxcursor1 libxdamage1 libxfixes3 \
        libxi6 libxinerama1 libxrandr2 libxkbcommon0 \
        libwayland-client0 libwayland-cursor0 libwayland-egl1 \
        libgl1 libegl1 libgles2 libgbm1 libdrm2 \
        libglib2.0-0 libpixman-1-0 libpng16-16 libjpeg-turbo8 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/adt

# Copy docker configuration only
COPY entrypoint.sh /entrypoint.sh
COPY qemu-wrapper.sh /qemu-wrapper-src.sh
COPY config.yaml /config-src.yaml

RUN chmod +x /entrypoint.sh /qemu-wrapper-src.sh

# Check if emulator files exist, if not download and extract
RUN bash -c '\
  if [ ! -d /opt/adt/tools/qemu/bin ]; then \
    echo "Downloading Aurora SDK..."; \
    mkdir -p /tmp/aurora-sdk; \
    cd /tmp/aurora-sdk; \
    echo "URL: $SDK_URL"; \
    curl -L --connect-timeout 30 --max-time 300 -o aurora-sdk.7z "$SDK_URL" 2>&1 || { echo "Download failed"; exit 1; }; \
    echo "Download complete, extracting..."; \
    ls -lh aurora-sdk.7z; \
    7z x aurora-sdk.7z -o/opt/adt 2>&1 || { echo "Extraction failed"; exit 1; }; \
    echo "Extraction complete"; \
    ls -la /opt/adt/ | head -20; \
  fi; \
  if [ ! -d /opt/adt/tools/qemu/bin ]; then \
    echo "ERROR: QEMU directory not found"; \
    echo "Contents of /opt/adt:"; \
    find /opt/adt -maxdepth 3 -type d 2>/dev/null | head -20; \
    exit 1; \
  fi; \
  true \
'

ENV LD_LIBRARY_PATH=/opt/adt/tools/qemu/lib
ENV PATH=/opt/adt/bin:$PATH

# Setup QEMU and ADT
RUN bash -c '\
  chmod +x /opt/adt/tools/qemu/bin/* /opt/adt/tools/qemu/libexec/* 2>/dev/null || true; \
  if [ -f /opt/adt/tools/qemu/bin/qemu-system-x86_64 ]; then \
    if [ ! -f /opt/adt/tools/qemu/bin/qemu-system-x86_64.real ]; then \
      mv /opt/adt/tools/qemu/bin/qemu-system-x86_64 /opt/adt/tools/qemu/bin/qemu-system-x86_64.real; \
    fi; \
  fi; \
  mkdir -p /opt/adt/emulators; \
  printf "%s\n" \
    "qemu_path = \"/opt/adt/tools/qemu/bin\"" \
    "qemu_install_path = \"/opt/adt/tools/qemu\"" \
    "default_device_index = 0" > /opt/adt/config.toml; \
  true \
'

# Install QEMU wrapper
COPY qemu-wrapper.sh /opt/adt/tools/qemu/bin/qemu-system-x86_64
RUN chmod +x /opt/adt/tools/qemu/bin/qemu-system-x86_64

# Каталоги для SSH-ключей (ключ для defaultuser и root создаётся в entrypoint)
RUN mkdir -p /opt/adt/ssh /root/.ssh && chmod 700 /root/.ssh

VOLUME ["/opt/adt/emulators"]

# SSH + VNC + VNC WebSocket
EXPOSE 2223 5901 5701

ENTRYPOINT ["/entrypoint.sh"]

STOPSIGNAL SIGTERM