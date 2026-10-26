FROM python:3.12-slim
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_DEFAULT_TIMEOUT=120
ARG PIP_RETRIES=5
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=${PIP_DEFAULT_TIMEOUT} \
    PIP_RETRIES=${PIP_RETRIES}
WORKDIR /srv
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN pip install --no-cache-dir "pypdf>=5.4,<7"
COPY packages/server-core/src/server_core /srv/server_core
COPY apps/server/app /srv/app
COPY apps/worker/worker_app /srv/worker_app
ENV PYTHONPATH=/srv
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
