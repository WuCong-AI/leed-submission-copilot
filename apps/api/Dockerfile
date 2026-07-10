FROM python:3.12-slim
WORKDIR /workspace
COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY packages ./packages
COPY data ./data
COPY apps/api ./apps/api
WORKDIR /workspace/apps/api
ENV PYTHONPATH=/workspace
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
