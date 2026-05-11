FROM ubuntu:22.04

LABEL maintainer="SEIII Agent Team"
LABEL description="Paper Reproduction Agent — Chainlit Frontend"
LABEL version="2.2.0"

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install Python 3.11 (runs the agent app / chainlit) and Python 3.7 (for legacy paper venvs)
# deadsnakes PPA provides pre-built packages — no source compilation needed
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common gnupg && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        python3.7 python3.7-venv python3.7-dev \
        git curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install pip for both Python versions
RUN python3.11 -m ensurepip --upgrade && \
    python3.7 -m ensurepip --upgrade

# Default to Python 3.7 for reproducing legacy papers (SimCLR, TensorFlow 1.x etc.)
ENV PYTHON_EXECUTABLE=/usr/bin/python3.7

# Pip mirror for faster downloads (override via PIP_INDEX_URL env var)
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Install Python dependencies (for the agent app, runs on Python 3.11)
COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY app/ ./app/
COPY .chainlit/ ./.chainlit/
COPY public/ ./public/
COPY chainlit.md ./

RUN mkdir -p /app/logs /app/data/memory /app/workspace

EXPOSE 8000

CMD ["chainlit", "run", "app/chainlit_app.py", "--host", "0.0.0.0", "--port", "8000"]
