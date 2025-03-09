FROM python:3.9-slim

WORKDIR /module

# Install required packages
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Copy module files
COPY semgrep_scan.py /module/
COPY config.yaml /module/
COPY rules /module/rules

CMD ["python3", "semgrep_scan.py"]