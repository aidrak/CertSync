#!/bin/bash
set -e

# Wait for PostgreSQL to be ready.
# This loop is crucial for robust startup in Docker Compose.
echo "Waiting for PostgreSQL database to be ready..."
until pg_isready -h database -p 5432 -U user; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done
echo "PostgreSQL is up and running!"

# Run database migrations
echo "Running database migrations with Alembic..."
echo "Current migration status:"
python -m alembic current
echo "Attempting to upgrade to head..."
python -m alembic upgrade head
echo "Alembic upgrade command finished."

echo "Starting CertSync application with Uvicorn..."
# Execute the main application command
exec uvicorn app.main:app --host 0.0.0.0 --port 8233 --reload
