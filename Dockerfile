# Base image pinned by tag; pin to a digest once you have pulled it:
#   docker pull python:3.11-slim && docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim
FROM python:3.11-slim

WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY gateway/ gateway/
COPY providers/ providers/
COPY network/ network/
COPY cache/ cache/
COPY config/ config/
COPY app/ app/

RUN mkdir -p logs
EXPOSE 8080
CMD ["uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "8080"]
