# Сначала получите JWT-токен:
#   curl -X POST http://localhost:8000/api/token/ \
#        -H "Content-Type: application/json" \
#        -d '{"username": "YOUR_USER", "password": "YOUR_PASSWORD"}'
# Подставьте access-токен в переменную TOKEN ниже.
TOKEN="<access-token>"

curl -X POST "http://localhost:8000/upload?server_id=1&original_filename=test.jpg&note=My%20photo&tags=nature,sunset&is_public=true" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/octet-stream" \
     --data-binary @"/path/to/your/file.jpg"
