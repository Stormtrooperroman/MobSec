FROM python:3.11-slim

WORKDIR /module

RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    curl \
    lsof \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt


COPY *.py /module/
COPY config.yaml /module/


ENV PORT=8091

EXPOSE 8091

CMD ["python3", "mitmproxy_server.py"]
