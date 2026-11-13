import logging
from typing import Optional

import requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from s_media_proxy.models import Server

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def upload_file(request):
    """
    Проксирует запрос на загрузку файла на соответствующий сервис.

    Query параметры:
    - server_id: ID сервера для загрузки (обязательный)
    - original_filename: оригинальное имя файла
    - note: заметка к файлу
    - tags: теги через запятую
    - is_public: публичный ли файл
    """
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return JsonResponse(
            {'error': 'Missing X-User-ID header'},
            status=400
        )

    server_id = request.GET.get('server_id')
    if not server_id:
        return JsonResponse(
            {'error': 'Missing server_id parameter'},
            status=400
        )

    # Получаем сервер
    try:
        server = Server.objects.get(id=server_id, user_id=user_id)
    except Server.DoesNotExist:
        return JsonResponse(
            {'error': f'Server with id={server_id} not found or access denied'},
            status=404
        )

    # Проверяем, можно ли добавлять на этот сервер
    if not server.can_add:
        return JsonResponse(
            {'error': f'Server "{server.name}" does not allow file uploads'},
            status=403
        )

    # Формируем URL для проксирования
    service_url = server.url.rstrip('/') + '/upload'

    # Передаем query параметры (кроме server_id)
    params = {}
    for key in ['original_filename', 'note', 'tags', 'is_public']:
        value = request.GET.get(key)
        if value is not None:
            params[key] = value

    # Подготавливаем заголовки
    headers = {
        'X-User-ID': user_id,
        'Content-Type': request.headers.get('Content-Type', 'application/octet-stream'),
    }

    # Проксируем запрос
    try:
        logger.info(
            f"Proxying upload to {service_url} for user {user_id}, "
            f"server {server.name} (id={server_id})"
        )

        response = requests.post(
            service_url,
            params=params,
            headers=headers,
            data=request.body,
            timeout=300,  # 5 минут для больших файлов
        )

        # Возвращаем ответ от сервиса
        return HttpResponse(
            response.content,
            status=response.status_code,
            content_type=response.headers.get('Content-Type', 'application/json')
        )

    except requests.exceptions.Timeout:
        logger.error(f"Timeout while uploading to {service_url}")
        return JsonResponse(
            {'error': 'Upload timeout'},
            status=504
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error while uploading to {service_url}: {e}")
        return JsonResponse(
            {'error': f'Cannot connect to service at {server.url}'},
            status=502
        )
    except Exception as e:
        logger.error(f"Unexpected error while uploading to {service_url}: {e}")
        return JsonResponse(
            {'error': 'Internal server error'},
            status=500
        )
