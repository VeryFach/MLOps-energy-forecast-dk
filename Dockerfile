FROM python:3.11-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir --timeout 120 --retries 5 ".[serving]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "energy_forecast.serving.serve_model:app", "--host", "0.0.0.0", "--port", "8000"]
