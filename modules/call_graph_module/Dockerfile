FROM python:3.11-slim

WORKDIR /module

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    liblmdb-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps (keep existing requirements.txt)
COPY requirements.txt ./
# Ensure lmdb is available — will be installed along with requirements if not present
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --no-cache-dir lmdb

# Copy module files
COPY call_graph_scan.py /module/
COPY config.yaml /module/

# Set Python to not buffer output
ENV PYTHONUNBUFFERED=1

# Performance optimizations (optional flags preserved from твоего Dockerfile)
ENV PYTHONOPTIMIZE=2
ENV PYTHONTHREADS=4
ENV PYTHONHASHSEED=random

# Memory settings: note — some of these envs may have limited effect inside container
ENV PYTHONMALLOC=malloc
ENV PYTHONDEVMODE=1

CMD ["python3", "-OO", "call_graph_scan.py"]
