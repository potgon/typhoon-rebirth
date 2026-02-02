# Use Python 3.12 slim as base
FROM python:3.12-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.12-slim

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash botuser

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/botuser/.local

# Make sure scripts in .local are usable
ENV PATH=/home/botuser/.local/bin:$PATH

# Copy application code
COPY --chown=botuser:botuser . .

# Create data directory for SQLite and logs
RUN mkdir -p /app/data && chown -R botuser:botuser /app/data

# Switch to non-root user
USER botuser

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "main.py"]
