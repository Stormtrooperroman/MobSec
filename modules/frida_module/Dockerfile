FROM python:3.11-slim

WORKDIR /module

RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    curl \
    nodejs \
    npm \
    wget \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY agent/package.json /module/agent/
RUN cd /module/agent && frida-create -t agent
RUN cd /module/agent && npm install frida-java-bridge

COPY *.py /module/
COPY frida_scripts/ /module/frida_scripts

COPY config.yaml /module/

ENV FRIDA_AGENT_ROOT=/module/agent
ENV FRIDA_SCRIPTS_DIR=/shared_data/frida_scripts
ENV PORT=8090

EXPOSE 8090

CMD ["python3", "frida_server.py"]
