FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

COPY --chown=app:app placeholder.py .

USER app
EXPOSE 8091
CMD ["python", "placeholder.py"]
