FROM python:3.12-slim
WORKDIR /app
COPY server.py adapters.py ./
COPY fixtures ./fixtures
RUN useradd -r appuser && mkdir -p data && chown -R appuser /app
USER appuser
ENTRYPOINT ["python", "server.py"]
