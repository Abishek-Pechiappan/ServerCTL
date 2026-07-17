# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm
WORKDIR /app

# iproute2 provides `ss` (collectors/ports.py). util-linux provides `last`/`who`
# (collectors/login_noti.py) reading the host's wtmp/utmp, bind-mounted in via
# docker-compose. Pinned to bookworm because the newer trixie-based slim image
# replaced `last` with wtmpdb (sqlite-backed), which can't read classic wtmp.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY authentication.py .
COPY agent ./agent

WORKDIR /app/agent
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
