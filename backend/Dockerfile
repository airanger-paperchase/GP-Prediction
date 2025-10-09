FROM python:3.11-slim-bullseye

# Minimal runtime image: no ODBC/DB drivers and no build tools.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only requirements first for caching
COPY requirements.txt /app/

# Upgrade pip and install pure-Python deps (no system build deps)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

# Create expected directories
RUN mkdir -p /app/artifacts /app/company_data || true

# Copy artifacts if present (no-op if directory missing)
RUN if [ -d "company_data/_default/artifacts" ]; then \
        cp -r company_data/_default/artifacts /app/default_company_data/_default/ || true; \
    fi || true

VOLUME /app/company_data

# Copy environment file into the image so python-dotenv (load_dotenv) can pick it up
# Note: keep secrets out of source control in production; this is for local/dev convenience
COPY .env /app/.env

# Run the app directly (no entrypoint script). The application uses python-dotenv to load /app/.env
EXPOSE 6514
CMD ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", "6514"]
