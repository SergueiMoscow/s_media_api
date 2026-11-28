import json
import logging
import uuid
from abc import ABC

import requests
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.db import connection
from django.http import HttpResponse
from rest_framework.request import Request

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # INFO, WARNING, ERROR или DEBUG

# Создаем обработчик логирования, который будет выводить сообщения в stderr
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)  # INFO, WARNING, ERROR или DEBUG

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

_SENSITIVE_FIELDS = (
    'key',
    'api_key',
    'analyzer_api_key',
    'service_api_key',
    'password',
    'secret',
)


def _mask_data(value):
    """Копия структуры с замаскированными секретными полями (для логов)."""
    if isinstance(value, dict):
        return {
            key: '***' if key in _SENSITIVE_FIELDS else _mask_data(val)
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_mask_data(item) for item in value]
    return value


def _base_url(url: str) -> str:
    """URL без query-строки — в ней могут быть имена файлов."""
    return url.split('?', 1)[0]


class ProxyViewMixin(ABC):
    timeout_proxy_request: int = 60

    def _proxy_request(
        self,
        request_url: str,
        request: Request,
        method: str,
        data=None,
        json_data=None,
        timeout: int = None,
        verify: bool = True,
        api_key: str = None,
        forward_request_body: bool = True,
    ):
        method_upper = method.upper()

        if isinstance(request.user, AnonymousUser):
            user_id = ''
        else:
            user_id = str(request.user.public_id)
        request_header = {
            'X-USER-ID': user_id,
            'X-REQUEST-ID': str(uuid.uuid4()),
        }
        if api_key:
            request_header['X-API-Key'] = api_key

        if data is None:
            data = {}

        # Поля сервера (`json_data`) не должны перезаписываться телом клиента.
        server_fields = json_data if isinstance(json_data, dict) else None

        out_data = dict(data)
        out_json = None
        is_get_or_delete = method_upper in ('GET', 'DELETE')

        if forward_request_body:
            content_type = request.content_type or ''
            is_multipart = 'multipart/form-data' in content_type
            is_json = 'application/json' in content_type

            if is_multipart:
                client_fields = {
                    key: value
                    for key, value in request.data.items()
                    if not isinstance(
                        value, (InMemoryUploadedFile, TemporaryUploadedFile)
                    )
                }
                # Сначала тело клиента, поверх — поля сервера (сервер побеждает).
                out_data = {**out_data, **client_fields, **(server_fields or {})}
            elif is_json and not request.FILES and not is_get_or_delete:
                if not isinstance(request.data, dict):
                    if server_fields:
                        # Тело не словарь, а вид ждёт словарь с серверными полями.
                        return HttpResponse(
                            json.dumps(
                                {'detail': 'Request body must be a JSON object'}
                            ),
                            status=400,
                            content_type='application/json',
                        )
                    out_json = request.data
                else:
                    merged = {**request.data, **(server_fields or {})}
                    if merged:
                        out_json = merged
            elif server_fields and not is_get_or_delete:
                # Тело не JSON и не multipart (например, без тела или
                # application/x-www-form-urlencoded) — серверные поля шлём JSON.
                out_json = server_fields

        if not forward_request_body and server_fields and not is_get_or_delete:
            out_json = server_fields

        # Логгируем детали запроса перед его выполнением (ключи маскируем).
        logger.info(f'Proxy request: {method_upper} {_base_url(request_url)}')
        if out_data:
            logger.debug(f'Proxy request data: {_mask_data(out_data)}')
        if out_json:
            logger.debug(f'Proxy request json data: {_mask_data(out_json)}')
        if request.FILES:
            logger.debug('Proxy request has files')

        # Закрываем соединение к БД перед блокирующим HTTP-запросом к узлу,
        # чтобы не удерживать соединение Postgres на время прокси-вызова.
        # Соединение переоткроется лениво при следующем обращении к ORM.
        connection.close()

        try:
            proxy_response = requests.request(
                method_upper,
                request_url,
                data=out_data,
                files=request.FILES,
                json=out_json,
                headers=request_header,
                timeout=self.timeout_proxy_request or timeout,
                verify=verify,
            )
        except requests.Timeout:
            logger.warning(f'Proxy timeout: {method_upper} {_base_url(request_url)}')
            return HttpResponse(
                json.dumps({'detail': 'Gateway Timeout'}),
                status=504,
                content_type='application/json',
            )
        except requests.ConnectionError:
            logger.warning(
                f'Proxy connection error: {method_upper} {_base_url(request_url)}'
            )
            return HttpResponse(
                json.dumps({'detail': 'Bad Gateway'}),
                status=502,
                content_type='application/json',
            )
        logger.info(f'Proxy response status code: {proxy_response.status_code}')

        response = HttpResponse(
            proxy_response.content,
            status=proxy_response.status_code,
            content_type=proxy_response.headers.get('Content-Type'),
        )

        return response
