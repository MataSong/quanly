FROM python:3.12-slim

# Non-root user for security (matches cap_drop ALL / no-new-privileges)
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Only runtime dependency: requests for HTTP callbacks to backend
# dual_ma.py is pure Python — no numpy/pandas needed
RUN pip install --no-cache-dir requests==2.32.3

# Copy runner and built-in strategy code
COPY runner.py .
COPY builtin/__init__.py builtin/__init__.py
COPY builtin/dual_ma.py builtin/dual_ma.py

# Read-only rootfs (tmpfs /tmp is mounted by the host docker run command)
# Switch to non-root
USER appuser

CMD ["python", "runner.py"]
