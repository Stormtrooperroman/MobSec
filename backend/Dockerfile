FROM python:3.11-slim

WORKDIR /app

RUN apt update -y && \
    apt install -y --no-install-recommends \
    postgresql && \
    apt upgrade -y && \
    apt autoremove -y && apt clean -y && rm -rf /var/lib/apt/lists/* /tmp/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED 1
ENV DATABASE_URL=postgresql+asyncpg://user:password@db:5432/mobsec
ENV REDIS_URL=redis://redis:6379/0

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]