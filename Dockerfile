FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
  && rm -rf /var/lib/apt/lists/*

COPY memory_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY memory_service/ ./memory_service/
COPY memory_client/ ./memory_client/
COPY mcp_server/ ./mcp_server/
COPY pyproject.toml ./

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "memory_service.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-config", "memory_service/logging.ini"]
