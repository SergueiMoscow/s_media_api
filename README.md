# s_media_api

Прослойка (backend) между фронтендом **s_media_front** и узловыми сервисами
**s_media_service** и **s_media_analyzer** комплекса **s_media** (каталогизатор
фото/видео).

API работает на хостинге; сервисы устанавливаются на компьютерах с локально
размещёнными фото и видео (NAS, домашний сервер и т.п.). API хранит реестр
узлов, проксирует запросы фронтенда к нужному узлу и проверяет авторизацию
(JWT).

## Стек

- Python 3.12, [Poetry](https://python-poetry.org/)
- Django 5 + Django REST Framework
- djangorestframework-simplejwt (JWT)
- requests (проксирование к узлам)
- PostgreSQL (продакшн) / SQLite (тесты)
- gunicorn + uvicorn (ASGI), pytest

## Структура

```
django_app/          # настройки Django (settings.py, settings_tests.py, urls.py)
s_media_proxy/       # приложение: модели, прокси-вьюхи, сериализаторы, репозиторий
s_media_proxy/views/ # вьюхи-прокси (catalog, storage, analyzer, upload, ...)
tests/               # pytest-тесты
deploy/              # nginx.conf и генерация self-signed сертификатов
docs/                # PROJECT.md, INTEGRATION.md
```

## Документация

- `docs/PROJECT.md` — полная картина проекта (архитектура, модели, эндпоинты,
  конфиг, запуск, тесты, решения и подводные камни) — для человека и агента.
- `docs/INTEGRATION.md` — интеграция с комплексом s_media (s_media_service,
  s_media_analyzer).

## Быстрый старт

```bash
poetry install
cp env.example .env          # заполнить SECRET_KEY, ALLOWED_HOSTS и т.д.
python manage.py migrate
python manage.py runserver
```

## Тесты

```bash
pytest                       # использует django_app.settings_tests (SQLite, --nomigrations)
```

