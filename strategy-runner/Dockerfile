FROM python:3.12-slim

# Non-root user for security (matches cap_drop ALL / no-new-privileges)
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# requests: HTTP callbacks to backend (live/poll mode).
# numpy + pandas: commonly used by user quant strategies (controlled-exec import
# whitelist allows them). PyPI official source — NOT the Tsinghua mirror, which is
# unreliable in some build environments (project lesson learned).
RUN pip install --no-cache-dir requests==2.32.3 \
    && pip install --no-cache-dir numpy pandas

# Copy runner and built-in strategy code
COPY runner.py .
COPY builtin/__init__.py builtin/__init__.py
COPY builtin/dual_ma.py builtin/dual_ma.py
COPY builtin/rsi.py builtin/rsi.py
COPY builtin/macd.py builtin/macd.py

# Read-only rootfs (tmpfs /tmp is mounted by the host docker run command)
# Switch to non-root
USER appuser

CMD ["python", "runner.py"]
