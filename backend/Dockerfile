# Use Python 3.11 to match local environment
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Set the working directory in the container
WORKDIR /app

# Install system dependencies with retry logic and error handling
RUN set -ex; \
    for i in 1 2 3; do \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            gcc \
            unixodbc-dev \
            unixodbc \
            gnupg2 \
            curl && \
        { rm -rf /var/lib/apt/lists/*; exit 0; } && break; \
        echo "Retrying package installation (attempt $i)..."; \
        sleep 5; \
    done || { echo "Failed to install system packages after 3 attempts"; exit 1; }

# Install ODBC Driver 18 for SQL Server with retry logic
RUN set -ex; \
    for i in 1 2 3; do \
        curl -f -sSL https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
        curl -f -sSL https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
        apt-get update && \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 && \
        { apt-get clean; rm -rf /var/lib/apt/lists/*; exit 0; } && break; \
        echo "Retrying ODBC driver installation (attempt $i)..."; \
        sleep 10; \
    done || { echo "Failed to install ODBC driver after 3 attempts"; exit 1; }

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies with retry
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Create necessary directories
RUN mkdir -p /app/artifacts \
    && mkdir -p /app/company_data

# Copy only the default artifacts if they exist
COPY artifacts/ /app/artifacts/

# Create a default company data structure if it doesn't exist
RUN mkdir -p /app/default_company_data/_default/artifacts

# Create default artifacts directory structure
RUN mkdir -p /app/default_company_data/_default/artifacts

# Copy artifacts if they exist, otherwise create an empty directory structure
RUN if [ -d "company_data/_default/artifacts" ] && [ "$(ls -A company_data/_default/artifacts)" ]; then \
        cp -r company_data/_default/artifacts/* /app/default_company_data/_default/artifacts/ && \
        chown -R 1000:1000 /app/default_company_data/_default/artifacts; \
    else \
        echo "No default artifacts found, using empty directory"; \
    fi

# Create a volume for company data
VOLUME /app/company_data

# Copy initialization script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Expose the port the app runs on
EXPOSE 6514

# Command to run the application
CMD ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", "6514"]
