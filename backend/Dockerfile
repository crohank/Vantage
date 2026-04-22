FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python application code
COPY agents/ ./agents/
COPY graph/ ./graph/
COPY tools/ ./tools/
COPY schemas/ ./schemas/
COPY services/ ./services/
COPY config.py .
COPY main.py .

# Create outputs directory
RUN mkdir -p /app/outputs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default command (can be overridden)
CMD ["python", "main.py"]