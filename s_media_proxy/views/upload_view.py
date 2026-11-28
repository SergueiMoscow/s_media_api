import logging

import requests
from django.http import HttpResponse, JsonResponse
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView

from s_media_proxy.repository import get_owned_server

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024


class UploadFileView(APIView):
    """Проксирует загрузку файла на соответствующий сервис.

    Query параметры:
    - server_id: ID сервера для загрузки (обязательный)
    - original_filename: оригинальное имя файла (обязательный для сервиса)
    - note: заметка к файлу
    - tags: теги через запятую
    - is_public: публичный ли файл
    """

    permission_classes = [permissions.IsAuthenticated]
    timeout = 300  # 5 минут для больших файлов

    def post(self, request):
        server_id = request.GET.get('server_id')
        if not server_id:
            return JsonResponse({'error': 'Missing server_id parameter'}, status=400)

        original_filename = request.GET.get('original_filename')
        if not original_filename:
            return JsonResponse(
                {'error': 'Missing original_filename parameter'}, status=400
            )

        # Входящий X-User-ID игнорируем: сервер ищется по server_id и текущему
        # пользователю (JWT), в сервис уходит request.user.public_id (UUID).
        try:
            server = get_owned_server(request, server_id)
        except NotFound:
            return JsonResponse(
                {'error': f'Server with id={server_id} not found or access denied'},
                status=404,
            )

        # Проверяем, можно ли добавлять на этот сервер
        if not server.can_add:
            return JsonResponse(
                {'error': f'Server "{server.name}" does not allow file uploads'},
                status=403,
            )

        service_url = server.url.rstrip('/') + '/upload'

        params = {}
        for key in ['original_filename', 'note', 'tags', 'is_public']:
            value = request.GET.get(key)
            if value is not None:
                params[key] = value

        headers = {
            'X-USER-ID': str(request.user.public_id),
            'Content-Type': request.headers.get(
                'Content-Type', 'application/octet-stream'
            ),
        }
        if server.service_api_key:
            headers['X-API-Key'] = server.service_api_key

        # Тело файла передаём потоком, не читая в память (request.body ограничен
        # DATA_UPLOAD_MAX_MEMORY_SIZE и не подходит для больших файлов).
        raw_request = request._request

        def body_stream():
            while True:
                chunk = raw_request.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

        try:
            logger.info(
                f'Proxying upload to {service_url} for server {server.name} (id={server_id})'
            )
            response = requests.post(
                service_url,
                params=params,
                headers=headers,
                data=body_stream(),
                timeout=self.timeout,
            )

            return HttpResponse(
                response.content,
                status=response.status_code,
                content_type=response.headers.get('Content-Type', 'application/json'),
            )

        except requests.exceptions.Timeout:
            logger.error(f'Timeout while uploading to {service_url}')
            return JsonResponse({'error': 'Upload timeout'}, status=504)
        except requests.exceptions.ConnectionError as e:
            logger.error(f'Connection error while uploading to {service_url}: {e}')
            return JsonResponse(
                {'error': f'Cannot connect to service at {server.url}'},
                status=502,
            )
        except Exception as e:
            logger.error(f'Unexpected error while uploading to {service_url}: {e}')
            return JsonResponse({'error': 'Internal server error'}, status=500)


upload_file = UploadFileView.as_view()
