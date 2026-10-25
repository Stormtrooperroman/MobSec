FROM python:3.11-slim

WORKDIR /module

# Install required packages
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Copy module files
COPY semgrep_scan.py /module/
COPY config.yaml /module/

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/Stormtrooperroman/MobSec-Semgrep-Mobile-Rules /tmp/semgrep_rules
RUN mv /tmp/semgrep_rules/rules /module/rules
RUN rm -rf /tmp/semgrep_rules
CMD ["python3", "semgrep_scan.py"]