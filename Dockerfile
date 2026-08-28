# Container for the FastAPI backend, deployed to Fly.io.
# The Streamlit UI is deployed separately by Streamlit Community Cloud and
# is not included here.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependencies first, so code edits do not invalidate the install layer.
COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

# Only what the API needs at runtime.
COPY app/ ./app/
COPY api/ ./api/
COPY migrations/ ./migrations/
COPY alembic.ini ./

EXPOSE 8080

# One worker: the app is I/O bound on the database, and a single connection
# pool avoids multiplying Neon connections by the worker count.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
