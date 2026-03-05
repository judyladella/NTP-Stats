FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY collector_service.py .
EXPOSE 8000
CMD ["python", "collector_service.py"]