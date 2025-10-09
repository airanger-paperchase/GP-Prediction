#!/bin/sh
set -e

# Create company data directory if it doesn't exist
if [ ! -d "/app/company_data" ]; then
    echo "Initializing company data directory..."
    mkdir -p /app/company_data
    
    # Copy default company data if the directory is empty
    if [ -d "/app/default_company_data" ]; then
        echo "Copying default company data..."
        cp -r /app/default_company_data/* /app/company_data/ 2>/dev/null || :
    fi
    
    # Set proper permissions
    chown -R 1000:1000 /app/company_data
    chmod -R 755 /app/company_data
fi

# Start the application
exec "$@"
