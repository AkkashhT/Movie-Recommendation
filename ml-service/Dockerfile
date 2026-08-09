FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl wget unzip && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install PyTorch CPU (enough for demo; swap --index-url for CUDA for GPU)
RUN pip install --no-cache-dir torch==2.3.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
