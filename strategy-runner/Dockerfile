FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple requests pandas numpy

COPY runner.py .

CMD ["python", "runner.py"]
