FROM python:3.14-slim@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4
WORKDIR /app
COPY backend /app/backend
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 verifai
USER verifai
EXPOSE 8000
CMD ["python", "-m", "verifai.server"]
