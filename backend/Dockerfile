FROM python:3.11-slim

WORKDIR /app

# Stage 1: Install system dependencies
RUN apt update -y && \
    apt install -y --no-install-recommends \
    postgresql \
    ffmpeg \
    adb \
    libsdl2-2.0-0 \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libavdevice-dev \
    libswresample-dev \
    libsdl2-dev \
    xz-utils \
    && apt clean

# Stage 2: Install build dependencies
RUN apt update -y && \
    apt install -y --no-install-recommends \
    gcc \
    pkg-config \
    meson \
    ninja-build \
    libusb-1.0-0 \
    libusb-1.0-0-dev \
    git \
    make \
    wget \
    ca-certificates \
    cmake \
    && apt clean

# Stage 3: Build and install scrcpy
RUN cd /tmp && \
    git clone https://github.com/Genymobile/scrcpy && \
    cd scrcpy && \
    wget https://github.com/Genymobile/scrcpy/releases/download/v3.3/scrcpy-server-v3.3 && \
    mkdir -p /usr/local/share/scrcpy && \
    mv scrcpy-server-v3.3 /usr/local/share/scrcpy/scrcpy-server && \
    meson setup build --buildtype=release --strip -Db_lto=true \
        -Dprebuilt_server=/usr/local/share/scrcpy/scrcpy-server && \
    cd build && \
    ninja && \
    ninja install

# Stage 4: Cleanup build dependencies
RUN apt remove -y \
    gcc \
    pkg-config \
    meson \
    ninja-build \
    git \
    make \
    cmake \
    && apt autoremove -y \
    && apt clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED 1
ENV DATABASE_URL=postgresql+asyncpg://user:password@db:5432/mobsec
ENV REDIS_URL=redis://redis:6379/0
ENV XDG_RUNTIME_DIR=/tmp/runtime-root

# Create XDG runtime directory with proper permissions
RUN mkdir -p /tmp/runtime-root && chmod 700 /tmp/runtime-root

# Expose ports for API and screen streaming
EXPOSE 8000 27183 27042

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]