FROM python:3.9-slim

WORKDIR /module

# Install git and required system packages
RUN apt-get update && apt-get install -y \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install TruffleHog and other requirements
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Copy module files
COPY trufflehog_scan.py /module/
COPY config.yaml /module/

CMD ["python3", "trufflehog_scan.py"] 