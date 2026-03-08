FROM python:3.9-slim

# Install dependencies
RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*
RUN pip install ntplib

WORKDIR /app

# CHANGE THIS: Copy both monitor.py and server.py
COPY *.py .

# Force logs to be visible
ENV PYTHONUNBUFFERED=1

# No default CMD needed as YAML overrides it, but we can add one for safety
CMD ["python3", "monitor.py"]