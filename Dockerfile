# ============================================================
# Agent Core Dockerfile
# ============================================================
# Purpose: Containerize the autonomous agent for paper reproduction
# Platform: Windows 11 compatible, Linux container

FROM python:3.11-slim

# ============================================================
# Metadata
# ============================================================
LABEL maintainer="SEIII Agent Team"
LABEL description="Autonomous Agent Core for Paper Reproduction"
LABEL version="1.0.0"

# ============================================================
# Environment Variables
# ============================================================
# Prevent Python from buffering output (important for container logs)
ENV PYTHONUNBUFFERED=1
# Set Python path
ENV PYTHONPATH=/app

# ============================================================
# Working Directory
# ============================================================
WORKDIR /app

# ============================================================
# Install System Dependencies
# ============================================================
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Copy Requirements First (for caching)
# ============================================================
COPY requirements.txt .

# ============================================================
# Install Python Dependencies
# ============================================================
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================
# Copy Application Code
# ============================================================
COPY app/ ./app/

# ============================================================
# Expose Ports (for Streamlit UI if enabled)
# ============================================================
EXPOSE 8501

# ============================================================
# Default Command
# ============================================================
# Run the agent with demo mode
CMD ["python", "-m", "app.main", "--mode", "demo"]
