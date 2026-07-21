FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY deploy/requirements-server.txt /tmp/requirements-server.txt
RUN pip install --no-cache-dir --timeout 45 --retries 5 \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/requirements-server.txt

COPY server /app/server
COPY client_v2/__init__.py client_v2/product.py client_v2/regions.py /app/client_v2/
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
COPY admin/dist /app/admin/dist
COPY assets /app/assets

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn server.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
