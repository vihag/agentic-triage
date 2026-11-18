FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

COPY db /src/db
COPY services/agent /src/services/agent
COPY contracts /src/contracts
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir /src/db /src/services/agent

COPY --chown=app:app services/api/app ./app

USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]