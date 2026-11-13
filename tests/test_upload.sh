curl -X POST "http://localhost:8000/upload?server_id=1&original_filename=test.jpg&note=My%20photo&tags=nature,sunset&is_public=true" \
     -H "X-User-ID: 1" \
     -H "Content-Type: application/octet-stream" \
     --data-binary @"/path/to/your/file.jpg"