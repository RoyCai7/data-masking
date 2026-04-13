FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user and storage directory
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /tmp/masking-service && chown appuser:appuser /tmp/masking-service \
    && mkdir -p /app/data && chown appuser:appuser /app/data

# Copy application code
COPY --chown=appuser:appuser . .

# Environment variables
ENV MAX_WORKERS=16
ENV PYTHONUNBUFFERED=1

USER appuser

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
