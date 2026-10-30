# Ground-station backend (FastAPI + simulation engine).
# Build context: repository root (needs shared/, simulator/, onboard/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv:/srv/ground-station/backend

RUN pip install --no-cache-dir uv==0.5.11
WORKDIR /srv
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY shared ./shared
COPY simulator ./simulator
COPY onboard ./onboard
COPY ground-station/backend ./ground-station/backend

RUN useradd --system --uid 10001 --home /srv app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
