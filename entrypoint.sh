#!/bin/sh
# Apply database migrations
echo "Applying database migrations"
python manage.py migrate --no-input

# Start the main process
echo "Starting application"
poetry run gunicorn django_app.asgi:application -k uvicorn.workers.UvicornWorker -b :8080
