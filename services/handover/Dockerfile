FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY contracts/requirements.txt /tmp/contracts-requirements.txt
COPY services/handover/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/contracts-requirements.txt -r /tmp/requirements.txt
COPY contracts/lazaro_contracts ./lazaro_contracts
COPY services/handover/handover ./handover
COPY scripts/vencer_casos.py ./vencer_casos.py
COPY scripts/purgar_datos.py ./purgar_datos.py
COPY scripts/avisar_vencimientos.py ./avisar_vencimientos.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn handover.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
