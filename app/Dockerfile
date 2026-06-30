# --- App tier: Flask served by gunicorn -----------------------------------
FROM python:3.12-slim

# Keep Python lean and predictable inside containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so they cache independently of app code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Run as a non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Wait for MySQL, create tables + seed, then hand off to gunicorn.
CMD ["python", "start.py"]
