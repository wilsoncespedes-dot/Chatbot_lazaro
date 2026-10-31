FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY contracts/requirements.txt /tmp/contracts-requirements.txt
COPY services/orchestrator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/contracts-requirements.txt -r /tmp/requirements.txt
COPY contracts/lazaro_contracts ./lazaro_contracts
COPY services/orchestrator/orchestrator ./orchestrator
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
