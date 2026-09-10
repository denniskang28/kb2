FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir .

COPY deploy/local /app/deploy/local
COPY tests/fixtures /app/tests/fixtures

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin kb2
USER 10001:10001

EXPOSE 8000
CMD ["uvicorn", "kb2_runtime.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
