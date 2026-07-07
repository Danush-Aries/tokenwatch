FROM python:3.12-slim

# Keep Python output unbuffered and skip .pyc files in the container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TOKENWATCH_DB=/data/tokenwatch.db

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install --no-cache-dir .

# Persist the SQLite database outside the image.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# The console script launches uvicorn on 0.0.0.0:8000.
CMD ["tokenwatch"]
