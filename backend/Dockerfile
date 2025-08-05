FROM python:3.11-slim

WORKDIR /app

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
    lsof \
    && apt clean

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