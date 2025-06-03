#!/bin/bash

echo "📦 Starting backend container..."

# Optional: navigate to app directory
cd /app

# Start supervisord (which launches FastAPI)
supervisord -c /app/supervisord.conf
