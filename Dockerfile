FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    ENVIRONMENT=production \
    QUANTUM_DB_PATH=/var/data/quantum_ai.sqlite3

WORKDIR /app

COPY requirements.txt requirements-test.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-test.txt

COPY app ./app
COPY tests ./tests
COPY static ./static
COPY run_bot.py .
COPY README.md .

# Run the complete pytest suite and the dedicated unittest safety suite.
RUN python -m compileall -q app tests \
    && python -m pytest -q tests \
    && python -m unittest discover -s tests -p 'test_deriv_trading.py' -v

RUN useradd --create-home --uid 10001 quantum \
    && mkdir -p /var/data \
    && chown -R quantum:quantum /app /var/data

USER quantum

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
