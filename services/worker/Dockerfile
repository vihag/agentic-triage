FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

COPY db /src/db
COPY services/agent /src/services/agent
COPY contracts /src/contracts
RUN pip install --no-cache-dir /src/db /src/services/agent

COPY --chown=app:app services/worker/worker.py services/worker/case_from_decision.py services/worker/fixtures.py ./

USER app
EXPOSE 8081
CMD ["python", "worker.py"]