#!/bin/sh
set -e

# Apply database migrations
echo "Applying database migrations"
python manage.py migrate --no-input

# Collect static files
echo "Collecting static files"
python manage.py collectstatic --no-input

# Start the main process
echo "Starting application"
gunicorn django_app.asgi:application -k uvicorn.workers.UvicornWorker -b :8080
