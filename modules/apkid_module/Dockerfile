FROM python:3.9-slim

WORKDIR /module

RUN apt-get update && apt-get install -y \
    build-essential \
    zlib1g-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements for Redis client
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Clone APKiD from GitHub and install
RUN git clone --recursive https://github.com/rednaga/APKiD.git /tmp/apkid \
    && cd /tmp/apkid \
    && pip3 install -e .


# Run prep-release.py to compile rules and then install APKiD
RUN cd /tmp/apkid \
    && python prep-release.py \
    && pip3 install -e .

# Copy module files
COPY apkid_scan.py /module/
COPY config.yaml /module/

CMD ["python3", "apkid_scan.py"]