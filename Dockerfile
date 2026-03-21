FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY scripts /app/scripts
COPY src /app/src
COPY samples /app/samples
COPY schemas /app/schemas
COPY docs /app/docs

RUN python -m pip install --no-cache-dir .

ENV PYTHONPATH=/app/src
ENV ATAS_MS_HOST=0.0.0.0
ENV ATAS_MS_PORT=8080
ENV ATAS_MS_DB_PATH=/app/data/market_structure.db

EXPOSE 8080 8090

CMD ["python", "-m", "atas_market_structure.server"]
