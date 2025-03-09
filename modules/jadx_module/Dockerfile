FROM openjdk:11-slim

# Install required system packages
RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-pip \
    wget \
    unzip \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /module

# Copy and install Python requirements
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Download and setup JADX
RUN wget https://github.com/skylot/jadx/releases/download/v1.5.1/jadx-1.5.1.zip && \
    mkdir -p /opt/jadx && \
    unzip jadx-1.5.1.zip -d /opt/jadx && \
    rm jadx-1.5.1.zip && \
    chmod +x /opt/jadx/bin/jadx

# Add JADX to PATH
ENV PATH=$PATH:/opt/jadx/bin

# Copy application files
COPY decompile.py /module/
COPY config.yaml /module/


# Set environment variables
ENV REDIS_URL=redis://redis:6379
ENV JADX_TIMEOUT=300

# Run the module
CMD ["python3", "decompile.py"]