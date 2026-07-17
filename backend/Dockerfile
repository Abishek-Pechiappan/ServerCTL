# syntax=docker/dockerfile:1

FROM python:3.12-slim
WORKDIR /app

# iproute2 provides `ss`, used by collectors/ports.py to read host listening ports
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY authentication.py .
COPY agent ./agent

WORKDIR /app/agent
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
