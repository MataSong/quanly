FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests pandas numpy

COPY runner.py .

CMD ["python", "runner.py"]
