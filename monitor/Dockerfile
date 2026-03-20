FROM python:3.9-slim

RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*
RUN pip install ntplib

WORKDIR /app
COPY *.py .

ENV PYTHONUNBUFFERED=1

CMD ["python3", "monitor.py"]