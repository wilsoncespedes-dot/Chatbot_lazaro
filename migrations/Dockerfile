FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "pg8000>=1.31,<2"
COPY migrations/__init__.py migrations/runner.py migrations/*.sql ./migrations/
RUN useradd --create-home --uid 10001 app
USER app
CMD ["python", "-m", "migrations.runner"]
