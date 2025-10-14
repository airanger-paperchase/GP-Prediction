# ---------------------------------------------------------
# Base Image — Debian 12 (Bookworm) with Python 3.11
# ---------------------------------------------------------
FROM python:3.11-slim-bookworm

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# ---------------------------------------------------------
# Install essential system dependencies and Microsoft ODBC Driver for SQL Server
# ---------------------------------------------------------
RUN set -eux; \
    rm -rf /var/lib/apt/lists/*; \
    echo 'Acquire::CompressionTypes::Order:: "gz";' > /etc/apt/apt.conf.d/99compression; \
    apt-get clean && apt-get update -o Acquire::Retries=3; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        build-essential \
        gcc \
        g++ \
        unixodbc \
        unixodbc-dev \
        libgomp1 \
        --fix-missing
# ---------------------------------------------------------
# Add Microsoft repository securely and install msodbcsql18
# ---------------------------------------------------------
RUN set -eux; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/microsoft-prod.list; \
    apt-get update -o Acquire::Retries=3; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/* /tmp/*



# ---------------------------------------------------------
# Set working directory and install Python dependencies
# ---------------------------------------------------------
WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------
# Copy application code and set non-root user
# ---------------------------------------------------------
COPY . .

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# ---------------------------------------------------------
# Expose port and define healthcheck
# ---------------------------------------------------------
EXPOSE 8007


HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

# ---------------------------------------------------------
# Default command to run the FastAPI/Starlette app with Uvicorn
# ---------------------------------------------------------
CMD ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", "8007", "--workers", "4"]
