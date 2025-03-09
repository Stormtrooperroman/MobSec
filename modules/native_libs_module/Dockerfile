FROM python:3.9-slim

WORKDIR /module

# Install system dependencies required for androguard
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install required packages
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy module files
COPY native_libs_scan.py /module/
COPY config.yaml /module/

CMD ["python3", "native_libs_scan.py"]