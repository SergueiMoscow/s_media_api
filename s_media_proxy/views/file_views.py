import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from django.contrib.auth.models import AnonymousUser
from django.db import connection, transaction
from django.http import StreamingHttpResponse
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from s_media_proxy.models import Server
from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import (
    get_all_servers,
    get_owned_server,
    get_server_by_id,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BaseAPIView(APIView):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = None
        self.storage_id = None
        self.folder = ''
        self.filename = None
        self.ip = None

    def get_additional_data(self, **kwargs):
        check_owner = kwargs.pop('check_owner', True)
        server_id = kwargs.get('server_id')
        if server_id is not None:
            if check_owner:
                self.server = get_owned_server(self.request, server_id)
            else:
                self.server = get_server_by_id(server_id)
                if self.server is None:
                    raise NotFound(detail='Server not found')
        if kwargs.get('storage_id'):
            self.storage_id = kwargs['storage_id']
        folder = (
            self.request.data.get('folder') or self.request.GET.get('folder') or None
        )
        if folder:
            self.folder = folder
        filename = self.request.data.get('filename') or self.request.GET.get('filename')
        if filename:
            self.filename = filename
        self._get_client_ip()

    def _get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            self.ip = x_forwarded_for.split(',')[0]
        else:
            self.ip = self.request.META.get('REMOTE_ADDR')


class CatalogFileViewSet(BaseAPIView, ProxyViewMixin):
    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        self.get_additional_data(server_id=server_id, storage_id=storage_id)
        # TO_DO Не доделано, добавить request!!!
        return Response(
            {
                'status': 'success',
                'count': 0,
                'results': {'folders': []},
            }
        )

    def post(self, request: Request, server_id: int, storage_id: uuid.UUID):
        self.get_additional_data(server_id=server_id, storage_id=storage_id)
        url = f'{self.server.url}/storage/fileinfo'
        additional_data = {
            'ip': self.ip,
            'storage_id': str(self.storage_id),
        }
        result = self._proxy_request(
            method='POST',
            request_url=url,
            request=request,
            json_data=additional_data,
            api_key=self.server.service_api_key or None,
        )

        # При удалении из каталога (status='inactive') дополнительно чистим связь
        # в анализаторе. Если анализатор недоступен или вернул ошибку — это не
        # повод ломать клиента: файл уже скрыт, связь исправит сверка.
        if (
            result.status_code < 400
            and (request.data or {}).get('status') == 'inactive'
            and self.server.analyzer_url
        ):
            self._clear_analyzer_link(result)
        return result

    def _clear_analyzer_link(self, response):
        try:
            payload = json.loads(response.content)
            file_id = payload['result']['id']
        except (ValueError, KeyError, TypeError):
            logger.warning(
                'fileinfo: cannot parse catalog file id for analyzer link cleanup'
            )
            return
        url = f'{self.server.analyzer_url.rstrip("/")}/catalog-files/{file_id}/link'
        headers = {'X-USER-ID': str(self.request.user.public_id)}
        if self.server.analyzer_api_key:
            headers['X-API-Key'] = self.server.analyzer_api_key
        try:
            resp = requests.delete(
                url, headers=headers, timeout=self.timeout_proxy_request
            )
            if resp.status_code >= 400:
                logger.warning(
                    f'fileinfo: analyzer link cleanup failed for {file_id}: HTTP {resp.status_code}'
                )
        except requests.RequestException as e:
            logger.warning(f'fileinfo: analyzer link cleanup failed for {file_id}: {e}')


class MainPageViewSet(APIView, ProxyViewMixin):

    # Главная доступна без JWT (её грузит лендинг).
    permission_classes = [permissions.AllowAny]
    timeout_proxy_request = 10  # таймаут на узел для главной страницы

    @transaction.non_atomic_requests
    def get(self, request: Request):
        servers = self.get_distinct_servers()
        if not servers:
            raise NotFound(detail="No servers found")

        files = []
        errors = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.fetch_data, server): server for server in servers
            }
            for future in as_completed(futures):
                server = futures[future]
                try:
                    files.extend(future.result())
                except Exception as e:
                    errors += 1
                    logger.warning(f'file_views.py: node {server.url} failed: {e}')

        if len(files) == 0:
            if errors and errors == len(servers):
                # Все узлы ответили ошибкой — не 404, а 502.
                return Response({'detail': 'Bad Gateway'}, status=502)
            raise NotFound(detail="No files found")
        # sorted_files = sorted(files, key=itemgetter('created_at'), reverse=True)  # сортировка по created_at
        files.sort(key=lambda file: file['created_at'], reverse=True)
        response = Response(
            {
                'status': 'success',
                'count': len(files),
                'results': {'files': files},
            }
        )
        return response

    def get_distinct_servers(self):
        all_servers = get_all_servers()
        # Сервера с одним `url` склеиваем: предпочитаем запись с заданным ключом.
        urls = {}
        for server in all_servers:
            existing = urls.get(server.url)
            if existing is None or (
                server.service_api_key and not existing.service_api_key
            ):
                urls[server.url] = server
        return list(urls.values())

    @transaction.non_atomic_requests
    def fetch_data(self, server: Server):
        request_url = urljoin(server.url, '/catalog/main')
        logger.info(f'file_views.py: fetching {server.url}')
        response = self._proxy_request(
            method='GET',
            request_url=request_url,
            request=self.request,
            api_key=server.service_api_key or None,
        )
        if response.status_code >= 400:
            raise RuntimeError(f'node returned HTTP {response.status_code}')
        data = json.loads(response.content)
        files = data['files']
        for file in files:
            file['server_id'] = server.id
        logger.info(f'file_views.py: end fetching {server.url}')
        return files


class BaseFileViewSet(BaseAPIView, ProxyViewMixin):

    # Фронт грузит preview/file через <img>/<video> без JWT.
    permission_classes = [permissions.AllowAny]

    action_path = ''
    connect_timeout = 5
    read_timeout = 60
    chunk_size = 64 * 1024

    # Заголовки, которые передаём клиенту как есть.
    passthrough_headers = {
        'Content-Length',
        'Content-Range',
        'Accept-Ranges',
        'Last-Modified',
        'ETag',
        'Cache-Control',
    }

    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        if request.GET.get('filename'):
            # Запрос на storage_id + folder + filename
            self.get_additional_data(
                server_id=server_id, storage_id=storage_id, check_owner=False
            )
            url = f'{self.server.url}/storage/{self.action_path}/{storage_id}?folder={self.folder}&filename={self.filename}'
        else:
            # Запрос на catalog по file_id.
            file_id = storage_id
            self.get_additional_data(server_id=server_id, check_owner=False)
            url = f'{self.server.url}/catalog/{self.action_path}/{file_id}'
        return self._stream_node_file(request, url)

    def _stream_node_file(self, request: Request, url: str):
        """Проксирует файл потоком, пробрасывая Range/If-Range."""
        if isinstance(request.user, AnonymousUser):
            user_id = ''
        else:
            user_id = str(request.user.public_id)
        headers = {
            'X-USER-ID': user_id,
            'X-REQUEST-ID': str(uuid.uuid4()),
        }
        if self.server.service_api_key:
            headers['X-API-Key'] = self.server.service_api_key
        # Пробрасываем Range/If-Range (видео-перемотка).
        for header in ('Range', 'If-Range'):
            value = request.META.get(f'HTTP_{header.upper().replace("-", "_")}')
            if value:
                headers[header] = value

        connection.close()

        node_response = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=(self.connect_timeout, self.read_timeout),
        )

        response = StreamingHttpResponse(
            self._iter_chunks(node_response),
            status=node_response.status_code,
            content_type=node_response.headers.get('Content-Type'),
        )
        for name in self.passthrough_headers:
            value = node_response.headers.get(name)
            if value is not None:
                response[name] = value
        return response

    def _iter_chunks(self, node_response):
        """Потоковая отдача чанков; соединение с узлом закрываем всегда."""
        try:
            for chunk in node_response.iter_content(chunk_size=self.chunk_size):
                if chunk:
                    yield chunk
        finally:
            node_response.close()


class FilePreviewViewSet(BaseFileViewSet):
    action_path = 'preview'


class FileViewSet(BaseFileViewSet):
    action_path = 'file'
