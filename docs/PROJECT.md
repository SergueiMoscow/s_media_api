# s_media_api — документация проекта

Полная картина проекта для человека и для агента (LLM/разработчика), которому
нужно вносить правки. Дополняет `docs/INTEGRATION.md` (интеграция с комплексом
s_media) — детали проксирования и взаимодействия с узловыми сервисами описаны
там.

---

## 1. Что это

`s_media_api` — прослойка (backend) между фронтендом **s_media_front** и
узловыми сервисами **s_media_service** и **s_media_analyzer** комплекса
**s_media** (каталогизатор фото/видео).

- API и фронт работают на хостинге.
- Сервисы ставятся на компьютерах с локально размещёнными фото/видео (NAS,
  домашний сервер и т.п.).
- API хранит реестр узлов (`Server`), проксирует запросы фронтенда к нужному
  узлу и проверяет авторизацию (JWT). Узловые сервисы доверяют API.

Стек: Python 3.12, Django 5 + Django REST Framework, djangorestframework-simplejwt
(JWT), requests, PostgreSQL (prod) / SQLite (тесты), gunicorn + uvicorn (ASGI),
pytest.

---

## 2. Архитектура

Один Django-проект, одно приложение `s_media_proxy`.

```
django_app/            # settings.py, settings_tests.py, urls.py, asgi.py, wsgi.py
s_media_proxy/         # models.py, serializers.py, repository.py, services.py,
                       # proxy_view_mixin.py, servers_views.py, image_generator.py
s_media_proxy/views/   # вьюхи-прокси по доменам
  catalog_views.py     # содержимое каталога
  file_views.py        # BaseAPIView, CatalogFileViewSet, MainPageViewSet, preview/file
  storage_views.py     # storages, содержимое, collage
  tag_views.py         # теги сервера
  upload_view.py       # загрузка файла на узел (APIView, JWT, поток)
  analyzer_views.py    # универсальный прокси в s_media_analyzer
  views.py             # users/groups (стандартные DRF-вьюсеты)
  membership_views.py  # оркестрация promote/unpromote (переключатель «в каталоге»)
s_media_proxy/migrations/
tests/                 # pytest-тесты
deploy/                # nginx.conf, gen_certificates.sh (self-signed SSL)
docs/                  # PROJECT.md, INTEGRATION.md
```

Точки входа:

- `django_app.asgi:application` — ASGI-приложение (в проде: gunicorn + uvicorn,
  порт 8080).
- `manage.py runserver` — разработка.

---

## 3. Модели

### User (`s_media_proxy.User`)

`AbstractUser` + поле `public_id` (UUID, уникальный). `public_id` — публичный
идентификатор, который отправляется на узлы в заголовке `X-USER-ID`.

### Server (узел)

| Поле | Назначение |
| --- | --- |
| `user` | владелец узла (FK на `User`) |
| `name` | название узла (≤ 20 символов) |
| `url` | базовый URL **s_media_service** (например `http://192.168.1.10:8081`) |
| `can_add` | разрешена ли загрузка файлов через `/upload` |
| `analyzer_url` | базовый URL **s_media_analyzer** (например `http://192.168.1.10:8000`); пусто — анализатор не настроен |
| `analyzer_api_key` | ключ для заголовка `X-API-Key` при обращении к анализатору |
| `service_api_key` | ключ для заголовка `X-API-Key` при обращении к сервису (`s_media_service`) |
| `created_at` | дата создания |

---

## 4. Проксирование к узлам

Базовый механизм — `ProxyViewMixin._proxy_request`
(`s_media_proxy/proxy_view_mixin.py`): делает `requests.request(...)` на
`{server.url}/<путь>` (или `{server.analyzer_url}/<путь>`) и возвращает
`HttpResponse` с телом/статусом/`Content-Type` ответа узла.

Заголовки запроса к узлу:

- `X-USER-ID` — `request.user.public_id` (пустая строка для анонима).
- `X-REQUEST-ID` — случайный UUID на каждый прокси-запрос.
- `X-API-Key` — добавляется, если в `_proxy_request` передан `api_key`
  (для сервиса — `Server.service_api_key`, для анализатора —
  `Server.analyzer_api_key`).

Особенности `_proxy_request`:

- `data`/`json_data` — JSON-тело и поля формы пробрасываются с приоритетом
  серверных полей: тело клиента кладётся первым, поверх него — поля сервера
  (`user_id`, `created_by`, `storage_id`, `ip`), так что подделать их из тела
  нельзя. Переданный словарь не мутируется. Если тело не словарь, а вид ждёт
  словарь с серверными полями — 400. Серверные поля шлются даже если тело не
  JSON и не multipart (POST без тела, `application/x-www-form-urlencoded`).
- `files=request.FILES` — проброс файлов.
- `timeout` — берётся из атрибута вьюхи `timeout_proxy_request` (по умолчанию 60).
- `verify` — по умолчанию `True` (self-signed сертификаты узлов — см.
  подводные камни).
- Сетевые ошибки: `requests.Timeout` → 504, `requests.ConnectionError` → 502
  (JSON `{"detail": "..."}`); в лог — warning с URL без query-строки и без ключей.
- `connection.close()` — перед блокирующим `requests.request` закрывается соединение
  к БД, чтобы не удерживать его на время прокси-вызова (защита от исчерпания
  `max_connections` при множестве параллельных запросов, например миниатюр
  анализатора). Соединение переоткрывается лениво при следующем обращении к ORM.
- Секретные поля (`key`, `api_key`, `password`, …) маскируются в debug-логах.

Потоковая отдача файлов: `/file/…` и `/preview/…` (`BaseFileViewSet`) не буферизуют
ответ узла — пробрасывают `Range`/`If-Range`, ходят в узел со `stream=True`
(таймаут `(connect=5, read=60)`), отдают `StreamingHttpResponse` чанками 64 КБ и
пробрасывают `Content-Range`/`Accept-Ranges`/`Last-Modified`/`ETag`/`Cache-Control`.

Универсальный прокси в анализатор — `AnalyzerProxyView`
(`s_media_proxy/views/analyzer_views.py`): поддерживает GET/POST/PUT/PATCH/DELETE
и пробрасывает query-string как есть. Внутренние пути (`persons/sync`,
`scanned-files/catalog-links`, `catalog-files/<uuid>/link`) закрыты (404), а из
ответа `POST /clusters/<id>/assign` вырезается `reference_embedding`. Подробнее —
`docs/INTEGRATION.md`.

---

## 5. API-эндпоинты

Аутентификация большинства эндпоинтов — JWT (заголовок `Authorization: Bearer ...`).
По умолчанию всё закрыто (`IsAuthenticated`); открыты (`AllowAny`) только
`/api/token/*`, `/main/`, `/preview/…`, `/file/…`, `/folders_image`.

| Метод и путь | Назначение |
| --- | --- |
| `POST /api/token/` | получить пару токенов (username/password) |
| `POST /api/token/refresh/` | обновить access-токен |
| `POST /api/token/verify/` | проверить токен |
| `/users/`, `/groups/` | стандартные DRF-вьюсеты (users/groups), только `IsAdminUser` |
| `/servers/` | CRUD узлов (`ServerViewSet`) |
| `GET/POST /storages/` | список/создание хранилищ (проксирует на все сервисы или на один по `server_id`) |
| `PATCH /storages/<storage_id>/` | обновление хранилища (`StorageDetailViewSet`) |
| `PATCH/DELETE /storages/<server_id>/<storage_id>/` | правка/удаление хранилища (`StorageViewSet`) |
| `GET /servers_content/` | сводка содержимого по всем серверам |
| `GET /storage/<server_id>/<storage_id>/` | содержимое хранилища |
| `GET /folders_image?folders=N` | генерация PNG-коллажа папок (локальная генерация, без JWT) |
| `GET /folder_collage/<server_id>/<storage_id>/` | коллаж папки |
| `GET /preview/<server_id>/<storage_id>/` | превью файла (без JWT, стриминг + `Range`) |
| `GET /file/<server_id>/<storage_id>/` | файл (без JWT, стриминг + `Range`) |
| `POST /storage/fileinfo/<server_id>/<storage_id>/` | добавить/изменить данные файла в каталоге |
| `GET /catalog/tags/<server_id>/` | теги сервера |
| `GET /main/` | главная страница (последние файлы по всем серверам, без JWT) |
| `GET /catalog_content/<server_id>/<storage_id>/` | содержимое каталога |
| `POST /upload?server_id=...` | загрузка файла (JWT, требует `can_add` у узла) |
| `/analyzer/<server_id>/` и `/analyzer/<server_id>/<path:analyzer_path>` | универсальный прокси в `s_media_analyzer` |
| `GET /analyzer/<server_id>/stats` | статус воркера анализатора (сводка) |
| `GET /analyzer/<server_id>/queue` | детальная очередь обработки анализатора |
| `POST /analyzer/<server_id>/clusters/<cluster_id>/promote` | добавить файлы кластера в каталог (оркестрация) |
| `POST /analyzer/<server_id>/clusters/<cluster_id>/unpromote` | убрать файлы кластера из каталога (оркестрация) |
| `POST /analyzer/<server_id>/faces/<face_id>/promote` | добавить файл лица в каталог (оркестрация) |
| `POST /analyzer/<server_id>/faces/<face_id>/unpromote` | убрать файл лица из каталога (оркестрация) |
| `/admin/` | Django admin |
| `/api-auth/` | browsable API login (DRF) |

---

## 6. Конфигурация (`.env`)

Читается через `environs` в `django_app/settings.py`.

| Переменная | Назначение |
| --- | --- |
| `SECRET_KEY` | секретный ключ Django |
| `DEBUG` | режим отладки (`true`/`false`) |
| `ALLOWED_HOSTS` | список хостов через запятую |
| `DATABASE_ENGINE` | `sqlite` или `postgresql` |
| `DATABASE_NAME` / `DATABASE_SCHEMA` / `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_HOST` / `DATABASE_PORT` | настройки PostgreSQL (для `DATABASE_ENGINE=postgresql`); схема задаётся через `search_path` |

---

## 7. Запуск и развёртывание

```bash
poetry install
cp env.example .env
python manage.py migrate
python manage.py runserver      # dev
```

Docker (см. `docker-compose.yml`):

- `s_media_api` — gunicorn + uvicorn, порт 8080 (expose, наружу не торчит).
- `s_media_api_db` — PostgreSQL (порт 5431).
- `s_media_api_migrations` — одноразовый контейнер `manage.py migrate`.
- `s_media_api_nginx` — nginx с self-signed SSL, слушает 8080 и проксирует на
  `s_media_api:8080`. Сертификаты генерирует `deploy/gen_certificates.sh`.

`entrypoint.sh` — применяет миграции и запускает gunicorn.

---

## 8. Тесты

```bash
pytest           # все тесты (SQLite, --nomigrations)
```

- Настройки тестов: `django_app/settings_tests.py` (SQLite, файл
  `test_db.sqlite3`), pytest-конфиг в `setup.cfg` (`[tool:pytest]`:
  `DJANGO_SETTINGS_MODULE = django_app.settings_tests`, `addopts =
  --nomigrations --strict-markers`).
- Фикстуры в `tests/conftest.py`: `auth_user`, `authorized_client`,
  `mock_request` (патчит `requests.request`), `created_user_and_server` и др.
- Фабрики — `tests/factories.py` (`UserFactory`).

Команда проверки миграций:

```bash
python manage.py makemigrations --settings django_app.settings_tests --check --dry-run
```

---

## 9. Ключевые решения и конвенции

- **Один узел = одна запись `Server`**, поля `url` (сервис) и `analyzer_url`
  (анализатор) — раздельные, т.к. сервисы слушают разные порты.
- **`X-USER-ID`** — сквозной идентификатор пользователя от API к узлам.
- **`X-API-Key`** — ключ узла: для сервиса — `Server.service_api_key`, для
  анализатора — `Server.analyzer_api_key`; оба `write_only` в сериализаторе и не
  возвращаются наружу.
- **Проверка владельца** — единая функция `get_owned_server(request, server_id)`
  (`s_media_proxy/repository.py`): сервера нет, он чужой или `server_id`
  некорректен (`None`, не число, `bool`) → 404. Используется во всех вьюхах,
  где `server_id` приходит из адреса/тела.
- **Прокси-вьюхи** — тонкие: решают узел по `server_id`, строят URL, вызывают
  `_proxy_request`, при необходимости обогащают ответ (`server_id`,
  `server_name`, `server_url`).
- Стиль кода: `Makefile` (`format`/`lint`/`test`), flake8 (max-complexity 10,
  max-line-length 120), black (skip-string-normalization), isort; строки ≤ 100
  (isort) / ≤ 120 (flake8).

---

## 10. Подводные камни

- **`verify=True`** в прокси: если узлы за self-signed сертификатами, прокси
  будет падать на проверке TLS. Для прод-узлов лучше использовать доверенные
  сертификаты либо продумать проброс `verify`.
- **`Server.can_add`** и **`Server.service_api_key`** появились позже остальных
  полей — убедиться, что миграции `0003_*` и `0004_*` накатаны в проде.
- **`static/` и `staticfiles/`** — `staticfiles/` это `STATIC_ROOT`
  (результат `collectstatic`), в git не коммитится.
- По умолчанию всё закрыто (`IsAuthenticated`); открыты только `/api/token/*`,
  `/main/`, `/preview/…`, `/file/…`, `/folders_image` — проверяй `permission_classes`
  каждой вьюхи отдельно.
- **`Range`/стриминг в nginx (stage)**: `/file/…` и `/preview/…` отдают видео
  потоком. Чтобы перемотка работала, nginx на stage должен не буферизовать
  (`proxy_buffering off`) и пробрасывать `Range`/`Accept-Ranges` — это зона
  деплой-агента, передать ему в отчёте.
