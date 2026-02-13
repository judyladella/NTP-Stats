FROM python:3.11-slim
WORKDIR /app
COPY . .
# Note: No CMD here, we control it via docker-compose