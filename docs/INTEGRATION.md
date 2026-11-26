# INTEGRATION.md — интеграция s_media_api с комплексом s_media

Документ фиксирует, как `s_media_api` встроен в комплекс **s_media**
(GitHub-пользователь `SergueiMoscow`): как он находит узлы и проксирует запросы
к `s_media_service` и `s_media_analyzer`. Дополняет `docs/PROJECT.md`.

---

## 1. Топология

- `s_media_front` (хостинг) обращается **только** к `s_media_api` (хостинг).
- `s_media_api` проксирует запросы к нужному узлу.
- На каждом узле работают два сервиса (обычно в Docker, своя PostgreSQL с
  pgvector):

| Сервис | Порт | Аутентификация | Что делает |
| --- | --- | --- | --- |
| `s_media_service` (FastAPI) | 8081 | `X-USER-ID` + `X-API-Key` | каталог фото/видео, storages, теги, fileinfo, upload |
| `s_media_analyzer` (FastAPI) | 8000 | `X-API-Key` (+ принимает `X-USER-ID`) | лица, кластеры, геотеги; пишет только в схему `analysis` |

---

## 2. Реестр узлов

Узлы хранятся в Django-модели `Server` (`s_media_proxy/models.py`).

| Поле | Назначение |
| --- | --- |
| `url` | базовый URL **s_media_service** (`http://<host>:8081`) |
| `analyzer_url` | базовый URL **s_media_analyzer** (`http://<host>:8000`); пусто — анализатор не настроен |
| `analyzer_api_key` | ключ для заголовка `X-API-Key` к анализатору |
| `service_api_key` | ключ для заголовка `X-API-Key` к сервису (`s_media_service`) |
| `can_add` | разрешена ли загрузка файлов через `/upload` |
| `user` | владелец узла |

Резолверы — `s_media_proxy/repository.py`: `get_server_by_id`, `get_servers_by_user`.

---

## 3. Проксирование в s_media_service

Механизм — `ProxyViewMixin._proxy_request` (`s_media_proxy/proxy_view_mixin.py`).

- URL: `{server.url}/<путь>` (без глобального префикса `/api/v1`).
- Заголовки: `X-USER-ID` = `request.user.public_id`, `X-REQUEST-ID` = UUID,
  `X-API-Key` = `server.service_api_key` (если задан).
- Ответ возвращается как есть (`HttpResponse` с телом/статусом/`Content-Type`).

Пример: `GET /catalog/tags/<server_id>/` → `GET {server.url}/catalog/tags`.

Вьюхи-прокси сервиса: `storage_views.py`, `catalog_views.py`, `file_views.py`,
`tag_views.py`, `upload_view.py` (см. `docs/PROJECT.md`, раздел эндпоинтов).

---

## 4. Проксирование в s_media_analyzer

Механизм — `AnalyzerProxyView` (`s_media_proxy/views/analyzer_views.py`),
универсальный прокси для всех методов.

- Маршруты API:
  - `/analyzer/<server_id>/` → корень анализатора (`GET /`).
  - `/analyzer/<server_id>/<path:analyzer_path>` → `{server.analyzer_url}/<analyzer_path>`.
- Query-string пробрасывается как есть (фильтры, пагинация).
- Заголовки к анализатору: `X-USER-ID` (текущий пользователь) и
  `X-API-Key` = `server.analyzer_api_key` (если задан).
- Проверки в API: JWT-аутентификация, сервер принадлежит текущему пользователю,
  `analyzer_url` задан (иначе 404).

Примеры:

- `GET /analyzer/5/clusters?unassigned=true` → `GET {analyzer_url}/clusters?unassigned=true`.
- `POST /analyzer/5/clusters/1/assign` → `POST {analyzer_url}/clusters/1/assign`.
- `PATCH /analyzer/5/faces/1` → `PATCH {analyzer_url}/faces/1`.

Список эндпоинтов анализатора — в `s_media_analyzer/docs/PROJECT.md` (раздел 6).

---

## 5. Оркестрация продвижения файла в каталог (реализовано)

Продвижение выполняет `s_media_api`, а не анализатор. Специальные вьюхи —
`s_media_proxy/views/membership_views.py`.

Поток `promote` (кластер/лицо):

1. `GET {analyzer_url}/clusters/{id}/promotable-files` (или `GET /faces/{id}`);
2. для каждого файла `POST {server.url}/storage/fileinfo` с телом
   `{ip, storage_id, folder_path, filename, add_tags: [name], status: 'active'}`
   (`add_tags` не стирает существующие теги; пустое имя — `add_tags` не шлётся;
   `status='active'` возвращает ранее убранный файл);
3. `PUT {analyzer_url}/scanned-files/catalog-links` со связями
   (`scanned_file_id`, `catalog_file_id`).

Поток `unpromote`: для каждого `catalog_file_id` — `POST {server.url}/storage/fileinfo`
с `status='inactive'`, затем очистка связи `catalog_file_id=null`.

Удаление файла из каталога (`POST /storage/fileinfo/...` с `status='inactive'`)
дополнительно чистит связь в анализаторе: `DELETE {analyzer_url}/catalog-files/{id}/link`.
Если анализатор недоступен или вернул ошибку — в лог пишется warning, а клиент
получает успешный ответ сервиса (файл уже скрыт, связь исправит сверка).

---

## 6. Права (реализовано)

По умолчанию всё закрыто: `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']` =
`IsAuthenticated`. Явно открыты (`AllowAny`) только:

- `/api/token/`, `/api/token/refresh/`, `/api/token/verify/`;
- `/main/`, `/preview/…`, `/file/…`, `/folders_image` — фронт грузит их через
  `<img>`/`<video>` без JWT.

`/users/` и `/groups/` доступны только администраторам (`IsAdminUser`).

Владелец узла проверяется единой функцией `get_owned_server(request, server_id)`
(`s_media_proxy/repository.py`): сервера нет или он чужой → 404. Она применяется
ко всем маршрутам, где `server_id` участвует в адресе или теле запроса. Для
`/preview` и `/file` владелец не проверяется (только существование сервера → 404),
так как доступ без JWT остаётся осознанно (подписанные ссылки — отдельный контракт).

Поля сервера (`user_id`, `created_by`, `storage_id`, `ip`, ключи) не могут быть
перезаписаны телом клиента: `_proxy_request` кладёт тело клиента первым, поверх —
поля сервера.

---

## 7. Расхождения и подводные камни

- **Разные порты**: `url` (service, 8081) и `analyzer_url` (analyzer, 8000) —
  раздельные поля `Server`, а не один URL.
- **`X-API-Key`** есть и у сервиса (`Server.service_api_key`), и у анализатора
  (`Server.analyzer_api_key`); ключи не путать и не логировать. `X-USER-ID` —
  UUID из `public_id`.
- **Формат ошибок узлов** — `{"error": {"error_code", "error_message"}}`
  (service и analyzer); API отдаёт тело ответа узла как есть.
- **`verify=True`** в прокси — self-signed сертификаты узлов потребуют решения
  (доверенные сертификаты или проброс `verify`).
- **`PUT /persons/sync`** — справочник людей + эталонные эмбеддинги от API к
  анализатору; требует хранения справочника людей в БД API (отдельная
  подзадача, см. ТЗ v2 раздел 15).
