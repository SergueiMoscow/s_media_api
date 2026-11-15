#!/bin/bash

# Директория для хранения сертификатов
CERT_DIR=/certs

# Создаём директорию если её нет
mkdir -p "$CERT_DIR"

# Проверяем, существуют ли сертификаты
if [ ! -f "$CERT_DIR/key.pem" ] || [ ! -f "$CERT_DIR/cert.pem" ]; then
    openssl req -x509 -nodes -newkey rsa:2048 -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" -days 365 \
        -subj "/C=US/ST=Denial/L=Springfield/O=Dis/CN=localhost"
fi