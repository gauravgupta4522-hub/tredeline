# Dockerfile — Render/any container host ke liye.
# Python app ko container me chalata hai.
FROM python:3.11-slim

WORKDIR /app

# pehle requirements copy + install (build cache ke liye)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# baaki saara code copy
COPY . .

# Render PORT env var deta hai; default 8000
ENV PORT=8000
EXPOSE 8000

# server start
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
