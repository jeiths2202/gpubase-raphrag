FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ofcode_server.py .
COPY indexer.py .
COPY web_doc_service.py .

# of7 source will be mounted at /data/of7 via docker-compose volume
# Index will be stored at /data/of7_index.json

EXPOSE 8000

CMD ["uvicorn", "ofcode_server:app", "--host", "0.0.0.0", "--port", "8000"]
