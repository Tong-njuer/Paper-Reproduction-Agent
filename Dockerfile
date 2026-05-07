FROM python:3.11-slim

LABEL maintainer="SEIII Agent Team"
LABEL description="Paper Reproduction Agent — Chainlit Frontend"
LABEL version="2.1.0"

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY app/ ./app/
COPY .chainlit/ ./.chainlit/
COPY public/ ./public/
COPY chainlit.md ./

RUN mkdir -p /app/logs /app/data/memory /app/workspace

EXPOSE 8000

CMD ["chainlit", "run", "app/chainlit_app.py", "--host", "0.0.0.0", "--port", "8000"]
